"""Disk cache for Datagrid converse results."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult

DEFAULT_CACHE_DIR = Path.cwd() / ".orchestrator" / "cache"


def cache_enabled() -> bool:
    raw = os.environ.get("DATAGRID_ORCH_CACHE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def cache_key(call: "AgentCall") -> str:
    payload = "|".join(
        [
            call.agent_id,
            call.chat_mode,
            call.conversation_id or "",
            call.prompt,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResultCache:
    """Simple JSON file cache keyed by agent/prompt hash."""

    def __init__(self, root: Path | None = None, *, ttl_seconds: int = 86_400) -> None:
        self.root = Path(root or os.environ.get("DATAGRID_ORCH_CACHE_DIR") or DEFAULT_CACHE_DIR)
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, call: "AgentCall") -> "AgentResult | None":
        from datagrid_agents.orchestrator.parallel import AgentResult

        if not cache_enabled():
            return None
        path = self.root / f"{cache_key(call)}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        saved_at = float(data.get("saved_at") or 0)
        if self.ttl_seconds > 0 and (time.time() - saved_at) > self.ttl_seconds:
            return None
        result = data.get("result") or {}
        credits = result.get("credits_consumed")
        try:
            credits_consumed = float(credits) if credits is not None else None
        except (TypeError, ValueError):
            credits_consumed = None
        return AgentResult(
            role=call.role,
            agent_id=str(result.get("agent_id") or call.agent_id),
            text=str(result.get("text") or ""),
            conversation_id=result.get("conversation_id"),
            error=result.get("error"),
            cached=True,
            credits_consumed=credits_consumed,
        )

    def put(self, call: "AgentCall", result: "AgentResult") -> None:
        if not cache_enabled() or result.error:
            return
        path = self.root / f"{cache_key(call)}.json"
        payload = {
            "saved_at": time.time(),
            "role": call.role,
            "result": {
                "agent_id": result.agent_id,
                "text": result.text,
                "conversation_id": result.conversation_id,
                "error": result.error,
                "credits_consumed": result.credits_consumed,
            },
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
