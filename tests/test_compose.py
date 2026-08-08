import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from datagrid_agents.cli import main
from datagrid_agents.orchestrator.compose import compose_plan, plan_heuristic
from datagrid_agents.orchestrator.dag import (
    DagCall,
    DagPlan,
    DagStage,
    execute_plan,
    validate_plan,
)
from datagrid_agents.orchestrator.parallel import AgentCall, run_parallel
from datagrid_agents.orchestrator.runner import run_compose


def test_heuristic_buyout_plan():
    plan = plan_heuristic("I am buying out my elec utility package")
    assert plan.planner == "heuristic"
    assert len(plan.stages) == 1
    roles = [c.role for c in plan.stages[0].calls]
    assert roles == ["mentor", "schedule", "change_order"]
    validate_plan(plan)


def test_heuristic_rfi_with_followup():
    plan = plan_heuristic(
        "Review RFI-12 then synthesize mentor lessons and schedule risks"
    )
    assert [s.id for s in plan.stages] == ["rfi_qa", "synthesize"]
    assert plan.stages[1].depends_on == ["rfi_qa"]
    assert [c.role for c in plan.stages[1].calls] == ["mentor", "schedule"]
    validate_plan(plan)


def test_heuristic_multistep_generic():
    plan = plan_heuristic(
        "First gather evidence from specs, then synthesize schedule and mentor risks"
    )
    assert [s.id for s in plan.stages] == ["gather", "synthesize"]
    validate_plan(plan)


def test_dag_cycle_rejected():
    plan = DagPlan(
        goal="x",
        stages=[
            DagStage("a", [DagCall("mentor")], depends_on=["b"]),
            DagStage("b", [DagCall("schedule")], depends_on=["a"]),
        ],
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_plan(plan)


def test_execute_plan_passes_prior_outputs():
    seen_prompts: list[str] = []

    def fake_converse(call: AgentCall):
        seen_prompts.append(call.prompt)
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"answer:{call.role}")],
            conversation_id=None,
        )

    plan = DagPlan(
        goal="goal",
        planner="manual",
        stages=[
            DagStage("gather", [DagCall("deep_search", "find stuff")]),
            DagStage(
                "synth",
                [DagCall("mentor", "synthesize")],
                depends_on=["gather"],
                include_prior=True,
            ),
        ],
    )
    results, summaries = execute_plan(plan, converse=fake_converse, max_workers=2)
    assert len(results) == 2
    assert [s["id"] for s in summaries] == ["gather", "synth"]
    assert any("Prior stage outputs" in p for p in seen_prompts)
    assert any("answer:gather:deep_search" in p for p in seen_prompts)


def test_compose_plan_llm_mode_with_stub():
    payload = {
        "goal": "custom",
        "planner": "llm",
        "rationale": "because",
        "stages": [
            {
                "id": "one",
                "name": "One",
                "depends_on": [],
                "calls": [{"role": "mentor", "focus": "risks", "repeats": 1}],
            }
        ],
    }

    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(payload))],
            conversation_id=None,
        )

    plan = compose_plan("custom", mode="llm", converse=fake_converse)
    assert plan.planner == "llm"
    assert plan.stages[0].calls[0].role == "mentor"


def test_run_compose_plan_only(tmp_path: Path):
    run = run_compose(
        "Buying out elec utility package risks",
        mode="heuristic",
        plan_only=True,
        runs_dir=tmp_path,
    )
    assert run.ok
    assert run.plan is not None
    assert run.results == []
    assert "buyout_risks" in run.markdown
    saved = list(tmp_path.glob("*.md")) + list(tmp_path.glob("*.json"))
    assert saved, f"expected plan artifacts in {tmp_path}"
    assert any("compose" in path.name for path in saved)


def test_run_compose_executes(tmp_path: Path):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"ok:{call.role}")],
            conversation_id=None,
        )

    run = run_compose(
        "Buying out elec utility package",
        mode="heuristic",
        converse=fake_converse,
        runs_dir=tmp_path,
    )
    assert run.ok
    assert len(run.results) == 3
    assert run.stages and run.stages[0]["id"] == "buyout_risks"


def test_cli_compose_plan_only(capsys):
    code = main(
        [
            "compose",
            "-p",
            "Buying out elec utility package",
            "--mode",
            "heuristic",
            "--plan-only",
            "--no-save",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["stages"][0]["id"] == "buyout_risks"


def test_cli_compose_with_dag_file(tmp_path: Path, monkeypatch, capsys):
    dag = {
        "goal": "from file",
        "planner": "manual",
        "stages": [
            {
                "id": "s1",
                "calls": [{"role": "mentor", "focus": "x"}],
            }
        ],
    }
    path = tmp_path / "dag.json"
    path.write_text(json.dumps(dag), encoding="utf-8")

    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text="ok")],
            conversation_id=None,
        )

    monkeypatch.setattr(
        "datagrid_agents.orchestrator.dag.run_parallel",
        lambda calls, max_workers=3, converse=None: run_parallel(
            calls, max_workers=max_workers, converse=fake_converse
        ),
    )
    code = main(
        [
            "compose",
            "--dag",
            str(path),
            "--no-save",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["role"] == "s1:mentor"
