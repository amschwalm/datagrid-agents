from pathlib import Path
from types import SimpleNamespace

from datagrid_agents.orchestrator import list_workflows, run_workflow
from datagrid_agents.orchestrator.context import gather_context
from datagrid_agents.orchestrator.differential import analyze_attachment_coverage
from datagrid_agents.orchestrator.merge import merge_results
from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult, run_parallel
from datagrid_agents.orchestrator.registry import list_roles, load_role
from datagrid_agents.orchestrator.workflows.fanout import configure as configure_fanout
from datagrid_agents.orchestrator.workflows.fanout import build_calls as build_fanout
from datagrid_agents.orchestrator.workflows.rfi_packet_qa import build_calls as build_rfi
from datagrid_agents.orchestrator.workflows.submittal_disposition import (
    build_calls as build_submittal,
)
from datagrid_agents.orchestrator.workflows.utility_buyout_risks import build_calls
from datagrid_agents.cli import main


def test_roles_include_core_agents():
    keys = {role.key for role in list_roles()}
    assert {
        "mentor",
        "schedule",
        "change_order",
        "deep_search",
        "drawing_revision",
        "rfi",
    } <= keys
    mentor = load_role("mentor")
    assert mentor.id
    assert mentor.chat_mode == "full_agent"


def test_role_env_override(monkeypatch):
    monkeypatch.setenv("DATAGRID_AGENT_MENTOR", "override-id-123")
    assert load_role("mentor").id == "override-id-123"


def test_list_workflows_includes_playbooks():
    names = set(list_workflows())
    assert {
        "utility_buyout_risks",
        "rfi_packet_qa",
        "submittal_disposition",
        "lessons_multipass",
        "fanout",
    } <= names


def test_build_calls_uses_three_roles():
    calls = build_calls("buy out elec utility", context="## Local\nnote")
    assert [c.role for c in calls] == ["mentor", "schedule", "change_order"]
    assert all("buy out elec utility" in c.prompt for c in calls)
    assert all("## Local" in c.prompt for c in calls)


def test_rfi_and_submittal_builders():
    rfi_calls = build_rfi("Review RFI-12", context="ctx")
    assert [c.role for c in rfi_calls] == [
        "deep_search",
        "drawings_specs",
        "drawing_revision",
    ]
    sub_calls = build_submittal("Disposition submittal", context="ctx")
    assert [c.role for c in sub_calls] == [
        "submittal",
        "drawings_specs",
        "deep_search",
    ]


def test_fanout_supports_repeats_same_agent():
    configure_fanout(["mentor"], repeats=2)
    calls = build_fanout("multi pass goal")
    assert [c.role for c in calls] == ["mentor#1", "mentor#2"]
    assert calls[0].agent_id == calls[1].agent_id == load_role("mentor").id
    assert "pass 1 of 2" in calls[0].prompt
    assert "pass 2 of 2" in calls[1].prompt


def test_run_parallel_preserves_order_and_isolates_errors():
    def fake_converse(call: AgentCall):
        if call.role == "schedule":
            raise RuntimeError("boom")
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"ok:{call.role}")],
            conversation_id=f"conv-{call.role}",
        )

    calls = [
        AgentCall("mentor", "a1", "p"),
        AgentCall("schedule", "a2", "p"),
        AgentCall("change_order", "a3", "p"),
    ]
    results = run_parallel(calls, converse=fake_converse, max_workers=3)
    assert [r.role for r in results] == ["mentor", "schedule", "change_order"]
    assert results[0].ok and results[0].text == "ok:mentor"
    assert not results[1].ok and "boom" in (results[1].error or "")
    assert results[2].ok


def test_gather_context_reads_files(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text("utility buyout notes", encoding="utf-8")
    text = gather_context([path])
    assert "Local repository context" in text
    assert "utility buyout notes" in text


def test_analyze_attachment_coverage(tmp_path: Path):
    present = tmp_path / "A-101.pdf"
    present.write_text("drawing", encoding="utf-8")
    missing = tmp_path / "missing-dir"
    analysis = analyze_attachment_coverage(
        "Review RFI-12 against A-101 and E-201",
        [present, missing],
    )
    assert "RFI-12" in analysis.upper() or "RFI-12" in analysis
    assert "A-101" in analysis
    assert "E-201" in analysis
    assert "without an obvious local file match" in analysis


def test_merge_results_builds_markdown():
    run = merge_results(
        workflow="utility_buyout_risks",
        prompt="goal",
        results=[
            AgentResult("mentor", "id1", "mentor answer", conversation_id="c1"),
            AgentResult("schedule", "id2", "", error="RuntimeError: x"),
        ],
        context="abc",
    )
    assert run.workflow == "utility_buyout_risks"
    assert "mentor answer" in run.markdown
    assert "Agent: schedule" in run.markdown
    assert run.ok is False
    assert run.context_chars == 3


def test_run_workflow_with_stub_converse(tmp_path: Path):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"reply:{call.role}")],
            conversation_id=f"cid-{call.role}",
        )

    note = tmp_path / "ctx.md"
    note.write_text("local ctx", encoding="utf-8")
    runs_dir = tmp_path / "runs"
    run = run_workflow(
        "utility_buyout_risks",
        "Buy out elec utility package",
        context_paths=[note],
        converse=fake_converse,
        runs_dir=runs_dir,
    )
    assert run.ok
    assert len(run.results) == 3
    assert any(runs_dir.glob("*.md"))
    assert any(runs_dir.glob("*.json"))


def test_run_fanout_workflow(tmp_path: Path):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"reply:{call.role}")],
            conversation_id=None,
        )

    run = run_workflow(
        "fanout",
        "custom combo",
        roles=["mentor", "schedule"],
        repeats=1,
        converse=fake_converse,
        runs_dir=tmp_path / "runs",
    )
    assert run.ok
    assert [r["role"] for r in run.results] == ["mentor", "schedule"]


def test_rfi_workflow_includes_differential(tmp_path: Path):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text="ok")],
            conversation_id=None,
        )

    drawing = tmp_path / "A-101.txt"
    drawing.write_text("sheet", encoding="utf-8")
    run = run_workflow(
        "rfi_packet_qa",
        "Review RFI-12 for A-101 and E-201",
        context_paths=[drawing],
        converse=fake_converse,
        runs_dir=None,
    )
    assert run.ok
    assert run.context_chars > 0
    assert "Local differential analysis" in run.markdown or run.context_chars > 50


def test_cli_roles_and_workflows(capsys):
    assert main(["roles"]) == 0
    out = capsys.readouterr().out
    assert "mentor" in out
    assert main(["workflows"]) == 0
    workflows_out = capsys.readouterr().out
    assert "utility_buyout_risks" in workflows_out
    assert "lessons_multipass" in workflows_out
    assert "fanout" in workflows_out


def test_cli_orchestrate_json(tmp_path: Path, monkeypatch, capsys):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"ok-{call.role}")],
            conversation_id=None,
        )

    monkeypatch.setattr(
        "datagrid_agents.orchestrator.runner.run_parallel",
        lambda calls, max_workers=None, converse=None, **kwargs: run_parallel(
            calls,
            max_workers=max_workers,
            converse=fake_converse,
            cache=False,
            **{k: v for k, v in kwargs.items() if k != "cache"},
        ),
    )
    code = main(
        [
            "orchestrate",
            "utility_buyout_risks",
            "-p",
            "risks please",
            "--no-save",
            "--no-register",
            "--no-cache",
            "--json",
        ]
    )
    assert code == 0
    payload = capsys.readouterr().out
    assert "utility_buyout_risks" in payload
    assert "ok-mentor" in payload


def test_cli_fanout_roles(monkeypatch, capsys):
    def fake_converse(call: AgentCall):
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"ok-{call.role}")],
            conversation_id=None,
        )

    monkeypatch.setattr(
        "datagrid_agents.orchestrator.runner.run_parallel",
        lambda calls, max_workers=None, converse=None, **kwargs: run_parallel(
            calls,
            max_workers=max_workers,
            converse=fake_converse,
            cache=False,
            **{k: v for k, v in kwargs.items() if k != "cache"},
        ),
    )
    code = main(
        [
            "orchestrate",
            "fanout",
            "--roles",
            "mentor,schedule",
            "--repeat",
            "2",
            "-p",
            "multi",
            "--no-save",
            "--no-register",
            "--no-cache",
            "--json",
        ]
    )
    assert code == 0
    payload = capsys.readouterr().out
    assert "mentor#1" in payload
    assert "mentor#2" in payload
    assert "schedule#1" in payload
