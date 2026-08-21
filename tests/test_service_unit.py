import json
from pathlib import Path
from types import SimpleNamespace

from datagrid_agents.registry import load_definition
from datagrid_agents import service


def test_knowledge_ids_for_reads_env(monkeypatch):
    definition = load_definition("rfi_reviewer")
    monkeypatch.setenv("CONSTRUCTION_KNOWLEDGE_IDS", "kn_a, kn_b")
    assert service.knowledge_ids_for(definition) == ["kn_a", "kn_b"]


def test_state_roundtrip(tmp_path: Path):
    path = tmp_path / "ids.json"
    service.save_state({"rfi_reviewer": "agent_123"}, path)
    assert service.load_state(path) == {"rfi_reviewer": "agent_123"}
    assert json.loads(path.read_text())["rfi_reviewer"] == "agent_123"


def test_resolve_agent_id_from_state(tmp_path: Path):
    path = tmp_path / "ids.json"
    service.save_state({"rfi_reviewer": "agent_abc"}, path)
    assert service.resolve_agent_id("rfi_reviewer", state_path=path) == "agent_abc"


def test_response_credits_from_object_and_dict():
    assert service.response_credits(SimpleNamespace(credits=SimpleNamespace(consumed=3.25))) == 3.25
    assert service.response_credits({"credits": {"consumed": 1}}) == 1.0
    assert service.response_credits(SimpleNamespace()) is None
