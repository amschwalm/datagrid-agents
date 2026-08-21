"""Tests for the stdlib Datagrid API orchestrator skill (no live network)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".cursor/skills/datagrid-orchestrator/scripts"
sys.path.insert(0, str(SCRIPTS))

import datagrid_client as dc  # noqa: E402
import explore as explore_mod  # noqa: E402
import orchestrate as orch  # noqa: E402


class FakeHTTPError(HTTPError):
    def __init__(self, code: int, body: bytes, headers=None):
        super().__init__("https://api.datagrid.com/v1/x", code, "err", headers or {}, io.BytesIO(body))


def _client(monkeypatch, handler):
    monkeypatch.setenv("DATAGRID_API_KEY", "dg_test_key")
    monkeypatch.delenv("Datagrid_API_KEY", raising=False)

    def fake_urlopen(req, timeout=None):
        return handler(req, timeout)

    monkeypatch.setattr(dc.urllib.request, "urlopen", fake_urlopen)
    return dc.DatagridClient(api_key="dg_test_key")


class _Resp:
    def __init__(self, payload, headers=None):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = headers or {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_whoami_and_auth_header(monkeypatch):
    seen = {}

    def handler(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["url"] = req.full_url
        return _Resp({"object": "identity", "user_id": "u1", "current_teamspace_id": "ts1", "teamspaces": []})

    client = _client(monkeypatch, handler)
    ident = client.whoami()
    assert ident["user_id"] == "u1"
    assert seen["auth"] == "Bearer dg_test_key"
    assert seen["url"].endswith("/identity")


def test_teamspace_header_not_query_param_on_knowledge(monkeypatch):
    seen = {}

    def handler(req, timeout):
        seen["header"] = req.get_header("Datagrid-teamspace") or req.get_header("Datagrid-Teamspace")
        seen["url"] = req.full_url
        return _Resp({"data": [{"id": "k1", "name": "Docs"}], "has_more": False})

    client = _client(monkeypatch, handler)
    items = client.list_knowledge(teamspace="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert items[0]["id"] == "k1"
    assert seen["header"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert "teamspace=" not in seen["url"]


def test_resolve_teamspace_name(monkeypatch):
    def handler(req, timeout):
        return _Resp(
            {
                "data": [
                    {"id": "b18c6015-084e-4ec3-9544-281b1a2ab964", "name": "KSA Demo"},
                    {"id": "11111111-1111-1111-1111-111111111111", "name": "Other"},
                ],
                "has_more": False,
            }
        )

    client = _client(monkeypatch, handler)
    assert client.resolve_teamspace("ksa demo") == "b18c6015-084e-4ec3-9544-281b1a2ab964"


def test_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(req, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeHTTPError(429, b'{"error":"rate"}')
        return _Resp({"object": "identity", "user_id": "u1", "current_teamspace_id": "ts", "teamspaces": []})

    monkeypatch.setattr(dc.time, "sleep", lambda *_: None)
    client = _client(monkeypatch, handler)
    assert client.whoami()["user_id"] == "u1"
    assert calls["n"] == 2


def test_converse_attaches_knowledge_corpus(monkeypatch):
    seen = {}

    def handler(req, timeout):
        seen["timeout"] = timeout
        seen["body"] = json.loads(req.data.decode())
        return _Resp(
            {
                "conversation_id": "conv-1",
                "content": [{"type": "output_text", "text": "hello"}],
                "tool_calls": [{"id": "t1"}],
                "credits": {"consumed": 0.5},
            }
        )

    client = _client(monkeypatch, handler)
    client.converse_timeout = 99
    resp = client.converse("hi", agent_id="agent-1", knowledge_ids=["kid-9"])
    assert dc.DatagridClient.converse_text(resp) == "hello"
    assert dc.DatagridClient.converse_credits(resp) == 0.5
    assert seen["body"]["config"]["corpus"][0]["knowledge_id"] == "kid-9"
    assert seen["timeout"] == 99


def test_looks_stalled():
    assert orch.looks_stalled("Please retry — I couldn't retrieve the data.", 0)
    assert orch.looks_stalled("", 5)
    assert not orch.looks_stalled("Change order 12 is unapproved. Source: CO log row 4.", 6)


def test_orchestrate_retries_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAGRID_API_KEY", "dg_test_key")

    class FakeClient:
        def __init__(self):
            self.calls = []

        def find_agent(self, name, teamspace=None):
            return {"id": "agent-1", "name": name}

        def converse(self, prompt, **kwargs):
            self.calls.append({"prompt": prompt, **kwargs})
            if len(self.calls) == 1:
                return {
                    "conversation_id": "conv-9",
                    "content": [{"text": "Please retry, I couldn't retrieve the data."}],
                    "tool_calls": [],
                    "credits": {"consumed": 0.1},
                }
            return {
                "conversation_id": "conv-9",
                "content": [{"text": "CO-12 is unapproved. Source: log."}],
                "tool_calls": [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}],
                "credits": {"consumed": 0.4},
            }

    fake = FakeClient()
    jobs = [{"tag": "co", "agent": "Change Order Agent", "prompt": "list unapproved COs"}]
    results = orch.run_jobs(
        jobs,
        out_dir=tmp_path,
        concurrency=1,
        default_teamspace=None,
        default_retries=2,
        client=fake,
    )
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["stalled"] is False
    assert results[0]["retries"] == 1
    assert fake.calls[1]["conversation_id"] == "conv-9"
    assert fake.calls[1]["prompt"] == orch.NUDGE
    assert (tmp_path / "co.json").exists()
    assert "stalled" in (tmp_path / "SUMMARY.md").read_text()


def test_explore_writes_profile(tmp_path):
    class FakeClient:
        def resolve_teamspace(self, name):
            return "b18c6015-084e-4ec3-9544-281b1a2ab964"

        def get_teamspace(self, ts_id):
            return {"id": ts_id, "name": "KSA Demo", "access": "closed"}

        def whoami(self):
            return {"user_id": "u1", "current_teamspace_id": "b18c6015-084e-4ec3-9544-281b1a2ab964"}

        def list_agents(self, teamspace=None):
            return [{"id": "agent-1", "name": "Mentor Agent", "description": "lessons"}]

        def list_knowledge(self, teamspace=None):
            return [{"id": "k1", "name": "Project Docs", "status": "ready"}]

        def get_knowledge(self, kid, teamspace=None):
            return {"id": kid, "name": "Project Docs", "status": "ready"}

        def list_tables(self, teamspace=None):
            return [
                {"id": "t1", "name": "COs", "knowledge_id": "k1"},
                {"id": "t2", "name": "Other", "knowledge_id": "zzz"},
            ]

        def ai_search(self, query, teamspace=None):
            return {"answer": f"answer for {query}"}

    profile = explore_mod.explore("KSA Demo", tmp_path, ["what exists?"], client=FakeClient())
    assert profile["teamspace"]["name"] == "KSA Demo"
    assert len(profile["tables"]) == 1
    assert (tmp_path / "profile.md").exists()
    jobs = json.loads((tmp_path / "jobs_template.json").read_text())
    assert jobs["jobs"][0]["agent_id"] == "agent-1"


def test_cli_whoami(monkeypatch, capsys):
    monkeypatch.setenv("DATAGRID_API_KEY", "dg_test_key")

    def handler(req, timeout):
        return _Resp({"object": "identity", "user_id": "u1", "current_teamspace_id": "ts", "teamspaces": []})

    monkeypatch.setattr(dc.urllib.request, "urlopen", handler)
    assert dc._cli(["whoami"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["user_id"] == "u1"


def test_missing_key(monkeypatch):
    monkeypatch.delenv("DATAGRID_API_KEY", raising=False)
    monkeypatch.delenv("Datagrid_API_KEY", raising=False)
    monkeypatch.setattr(dc, "_load_dotenv_files", lambda: None)
    with pytest.raises(dc.DatagridError):
        dc.resolve_api_key("")
