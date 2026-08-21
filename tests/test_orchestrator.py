from types import SimpleNamespace

from datagrid_agents.cli import main
from datagrid_agents.orchestrator.parallel import AgentCall, run_parallel
from datagrid_agents.orchestrator.registry import list_roles, load_role
from datagrid_agents.orchestrator.skill_bridge import skill_scripts_dir


def test_roles_include_core_agents():
    keys = {role.key for role in list_roles()}
    assert {
        "mentor",
        "schedule",
        "change_order",
        "deep_search",
        "drawing_revision",
        "rfi",
        "lessons_extractor",
    } <= keys
    mentor = load_role("mentor")
    assert mentor.id
    assert mentor.chat_mode == "full_agent"


def test_role_env_override(monkeypatch):
    monkeypatch.setenv("DATAGRID_AGENT_MENTOR", "override-id-123")
    assert load_role("mentor").id == "override-id-123"


def test_skill_scripts_exist():
    scripts = skill_scripts_dir()
    assert (scripts / "datagrid_client.py").is_file()
    assert (scripts / "explore.py").is_file()
    assert (scripts / "orchestrate.py").is_file()


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


def test_run_parallel_on_result_callback():
    seen: list[str] = []

    def fake_converse(call: AgentCall):
        return SimpleNamespace(content=[SimpleNamespace(text=call.role)], conversation_id="c")

    def on_result(index, call, result):
        seen.append(f"{index}:{result.text}")

    calls = [AgentCall("mentor", "a1", "p"), AgentCall("schedule", "a2", "p")]
    run_parallel(calls, converse=fake_converse, max_workers=2, on_result=on_result)
    assert len(seen) == 2


def test_run_parallel_respects_max_calls():
    calls = [AgentCall("mentor", "a1", "p") for _ in range(3)]
    try:
        run_parallel(calls, max_calls=2, converse=lambda c: SimpleNamespace(content=[]))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "max_calls" in str(exc)


def test_run_parallel_uses_skill_stall_retry(monkeypatch):
    client_mod, orch_mod = __import__(
        "datagrid_agents.orchestrator.skill_bridge", fromlist=["load_skill_modules"]
    ).load_skill_modules()

    calls_made = {"n": 0}

    class FakeClient:
        pass

    def fake_run_one(client, job, default_teamspace=None, default_retries=2):
        calls_made["n"] += 1
        assert job["agent_id"] == "agent-1"
        assert default_retries == 2
        return {
            "tag": job["tag"],
            "text": "CO-12 unapproved",
            "conversation_id": "conv-1",
            "credits": 0.4,
            "stalled": False,
            "retries": 1,
            "error": None,
        }

    monkeypatch.setattr(orch_mod, "run_one", fake_run_one)
    monkeypatch.setattr(client_mod, "DatagridClient", lambda **kwargs: FakeClient())

    results = run_parallel(
        [AgentCall("mentor", "agent-1", "list COs")],
        max_workers=1,
        max_retries=2,
    )
    assert results[0].ok
    assert results[0].text == "CO-12 unapproved"
    assert results[0].retries == 1
    assert calls_made["n"] == 1


def test_cli_roles_and_help(capsys):
    assert main(["roles"]) == 0
    out = capsys.readouterr().out
    assert "mentor" in out
    assert "lessons_extractor" in out


def test_cli_orchestrate_requires_jobs_or_agents():
    code = main(["orchestrate"])
    assert code in {1, 2}
