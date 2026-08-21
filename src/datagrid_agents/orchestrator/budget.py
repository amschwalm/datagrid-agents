"""Budgets and defaults for orchestration calls."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class OrchestratorBudget:
    """Runtime limits for Datagrid fan-out."""

    max_workers: int = 3
    timeout_seconds: float = 120.0
    max_calls: int = 12
    default_chat_mode: str = "full_agent"

    @classmethod
    def from_env(
        cls,
        *,
        max_workers: int | None = None,
        timeout_seconds: float | None = None,
        max_calls: int | None = None,
    ) -> "OrchestratorBudget":
        workers = max_workers if max_workers is not None else _env_int(
            "DATAGRID_ORCH_MAX_WORKERS", 3
        )
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("DATAGRID_ORCH_TIMEOUT_SECONDS", "120") or 120)
        )
        calls = max_calls if max_calls is not None else _env_int(
            "DATAGRID_ORCH_MAX_CALLS", 12
        )
        chat_mode = (
            os.environ.get("DATAGRID_ORCH_CHAT_MODE", "full_agent").strip()
            or "full_agent"
        )
        if workers < 1:
            raise ValueError("max_workers must be >= 1")
        if timeout <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if calls < 1:
            raise ValueError("max_calls must be >= 1")
        return cls(
            max_workers=workers,
            timeout_seconds=timeout,
            max_calls=calls,
            default_chat_mode=chat_mode,
        )
