from pathlib import Path
from types import SimpleNamespace

import pytest

from datagrid_agents.orchestrator.budget import OrchestratorBudget
from datagrid_agents.orchestrator.cache import ResultCache
from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult, run_parallel
from datagrid_agents.orchestrator.runner import run_workflow
from datagrid_agents.orchestrator.synthesize import synthesize_results


def test_budget_from_env(monkeypatch):
    monkeypatch.setenv("DATAGRID_ORCH_MAX_WORKERS", "4")
    monkeypatch.setenv("DATAGRID_ORCH_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("DATAGRID_ORCH_MAX_CALLS", "5")
    budget = OrchestratorBudget.from_env()
    assert budget.max_workers == 4
    assert budget.timeout_seconds == 30
    assert budget.max_calls == 5


def test_run_parallel_respects_max_calls():
    calls = [AgentCall(f"r{i}", "id", "p") for i in range(3)]
    with pytest.raises(ValueError, match="max_calls"):
        run_parallel(calls, max_calls=2, cache=False)


def test_result_cache_roundtrip(tmp_path: Path):
    cache = ResultCache(tmp_path, ttl_seconds=60)
    call = AgentCall("mentor", "agent-1", "prompt-a")
    result = AgentResult("mentor", "agent-1", "hello", conversation_id="c1")
    cache.put(call, result)
    hit = cache.get(call)
    assert hit is not None
    assert hit.text == "hello"
    assert hit.conversation_id == "c1"


def test_run_parallel_uses_cache(tmp_path: Path):
    cache = ResultCache(tmp_path, ttl_seconds=60)
    call = AgentCall("mentor", "agent-1", "same prompt")
    cache.put(call, AgentResult("mentor", "agent-1", "cached-text"))

    def boom(_call: AgentCall):
        raise AssertionError("should not call converse on cache hit")

    results = run_parallel([call], cache=cache, converse=boom, max_workers=1)
    assert results[0].cached is True
    assert results[0].text == "cached-text"


def test_synthesize_dedupes_similar_risks():
    results = [
        AgentResult(
            "mentor",
            "a1",
            """
| Risk | Why it matters | Preventative action |
| --- | --- | --- |
| Undocumented utility conflicts | Causes stop-work and redesign | Mandate GPR/potholing |
| Late utility coordination | Critical path delays | Start utility study early |

### Recommended next action
Schedule a pre-excavation coordination meeting.
""",
        ),
        AgentResult(
            "schedule",
            "a2",
            """
| Risk | Why it matters | Preventative action |
| --- | --- | --- |
| Utility Conflict Discovery | Undiscovered lines halt excavation | Mandate comprehensive GPR |
| Lead time for switchgear | Delays energization | Secure early submittals |
""",
        ),
    ]
    synthesis = synthesize_results(
        results, prompt="buyout risks", workflow="utility_buyout_risks"
    )
    titles = [item.title.lower() for item in synthesis.items]
    assert any("utility" in title and "conflict" in title for title in titles)
    # Similar utility-conflict rows should collapse toward one stronger item.
    conflictish = [
        item
        for item in synthesis.items
        if "conflict" in item.title.lower() or "utility conflict" in item.title.lower()
    ]
    assert len(conflictish) <= 2
    assert "Checklist" in synthesis.markdown
    assert synthesis.next_actions


def test_run_workflow_writes_register(tmp_path: Path):
    def fake_converse(call: AgentCall):
        text = """
| Risk | Why it matters | Preventative action |
| --- | --- | --- |
| Scope overlap | Gaps between trades | Pre-award scope review |
"""
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            conversation_id=None,
        )

    runs_dir = tmp_path / "runs"
    register_dir = tmp_path / "registers"
    run = run_workflow(
        "utility_buyout_risks",
        "Buying out elec utility package",
        converse=fake_converse,
        cache=False,
        runs_dir=runs_dir,
        register_dir=register_dir,
        write_register=True,
    )
    assert run.ok
    assert run.synthesis is not None
    assert run.register_markdown
    assert any(register_dir.glob("*risk_register.md"))
    assert run.artifact_paths
    assert "Artifacts" in run.markdown
