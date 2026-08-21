"""Parallel Datagrid converse via the stdlib orchestrator skill."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from datagrid_agents.orchestrator.skill_bridge import load_skill_modules

OnResultCallback = Callable[[int, "AgentCall", "AgentResult"], None]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentCall:
    """One Datagrid converse request."""

    role: str
    agent_id: str
    prompt: str
    chat_mode: str = "full_agent"
    conversation_id: str | None = None
    teamspace: str | None = None
    knowledge_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentResult:
    """Outcome of one Datagrid converse request."""

    role: str
    agent_id: str
    text: str
    conversation_id: str | None = None
    error: str | None = None
    cached: bool = False
    credits_consumed: float | None = None
    stalled: bool = False
    retries: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and not self.stalled


def _execute_stub(call: AgentCall, converse: Callable[[AgentCall], Any]) -> AgentResult:
    try:
        response = converse(call)
        text = ""
        conversation_id = None
        credits = None
        if hasattr(response, "content") or hasattr(response, "conversation_id"):
            from datagrid_agents import service

            text = service.response_text(response)
            conversation_id = getattr(response, "conversation_id", None)
            credits = service.response_credits(response)
        elif isinstance(response, dict):
            client_mod, _ = load_skill_modules()
            text = client_mod.DatagridClient.converse_text(response)
            conversation_id = response.get("conversation_id")
            credits = client_mod.DatagridClient.converse_credits(response)
        else:
            text = str(response or "")
        return AgentResult(
            role=call.role,
            agent_id=call.agent_id,
            text=text,
            conversation_id=conversation_id,
            credits_consumed=credits,
        )
    except Exception as exc:  # noqa: BLE001 - surface per-agent failures
        return AgentResult(
            role=call.role,
            agent_id=call.agent_id,
            text="",
            error=f"{type(exc).__name__}: {exc}",
        )


def _execute_skill(
    call: AgentCall,
    *,
    teamspace: str | None,
    max_retries: int,
    client: Any | None = None,
) -> AgentResult:
    client_mod, orch_mod = load_skill_modules()
    dg = client or client_mod.DatagridClient(teamspace=call.teamspace or teamspace)
    job = {
        "tag": (call.role or "job").replace(":", "-").replace("#", "-"),
        "agent_id": call.agent_id,
        "prompt": call.prompt,
        "conversation_id": call.conversation_id,
        "chat_mode": call.chat_mode or "full_agent",
        "max_retries": max_retries,
        "knowledge_ids": list(call.knowledge_ids or ()),
        "teamspace": call.teamspace or teamspace,
    }
    raw = orch_mod.run_one(
        dg,
        job,
        default_teamspace=call.teamspace or teamspace,
        default_retries=max_retries,
    )
    error = raw.get("error")
    stalled = bool(raw.get("stalled"))
    return AgentResult(
        role=call.role,
        agent_id=call.agent_id,
        text=raw.get("text") or "",
        conversation_id=raw.get("conversation_id"),
        error=error,
        credits_consumed=raw.get("credits"),
        stalled=stalled,
        retries=int(raw.get("retries") or 0),
    )


def run_parallel(
    calls: list[AgentCall],
    *,
    max_workers: int | None = None,
    timeout_seconds: float | None = None,
    max_calls: int | None = None,
    budget: Any = None,  # unused; kept so callers do not break
    cache: Any = None,  # unused; skill orchestrator writes per-job files instead
    converse: Callable[[AgentCall], Any] | None = None,
    on_result: OnResultCallback | None = None,
    teamspace: str | None = None,
    max_retries: int | None = None,
    client: Any | None = None,
) -> list[AgentResult]:
    """Run Datagrid agent calls concurrently; preserve input order in results.

    Default converse path is the stdlib skill orchestrator (stall retries).
    Pass `converse=` to stub in tests.
    """
    del budget, cache
    if not calls:
        return []

    workers = _env_int("DATAGRID_ORCH_MAX_WORKERS", 6) if max_workers is None else max_workers
    timeout = (
        _env_float("DATAGRID_ORCH_TIMEOUT_SECONDS", 3600.0)
        if timeout_seconds is None
        else timeout_seconds
    )
    call_budget = _env_int("DATAGRID_ORCH_MAX_CALLS", 100) if max_calls is None else max_calls
    retries = _env_int("DATAGRID_ORCH_MAX_RETRIES", 2) if max_retries is None else max_retries

    if len(calls) > call_budget:
        raise ValueError(
            f"refusing to run {len(calls)} calls; max_calls budget is {call_budget}"
        )

    workers = max(1, min(workers, len(calls)))
    results: dict[int, AgentResult] = {}
    pending: dict[Any, int] = {}

    def _store(index: int, result: AgentResult) -> None:
        results[index] = result
        if on_result is not None:
            on_result(index, calls[index], result)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, call in enumerate(calls):
            if converse is not None:
                future = pool.submit(_execute_stub, call, converse)
            else:
                future = pool.submit(
                    _execute_skill,
                    call,
                    teamspace=teamspace,
                    max_retries=retries,
                    client=client,
                )
            pending[future] = index

        try:
            for future in as_completed(pending, timeout=timeout if pending else None):
                index = pending[future]
                try:
                    result = future.result(timeout=0)
                except FuturesTimeoutError:
                    result = AgentResult(
                        role=calls[index].role,
                        agent_id=calls[index].agent_id,
                        text="",
                        error=f"TimeoutError: call exceeded {timeout}s",
                    )
                _store(index, result)
        except FuturesTimeoutError:
            for future, index in pending.items():
                if index in results:
                    continue
                future.cancel()
                _store(
                    index,
                    AgentResult(
                        role=calls[index].role,
                        agent_id=calls[index].agent_id,
                        text="",
                        error=f"TimeoutError: stage exceeded {timeout}s",
                    ),
                )

    return [results[i] for i in range(len(calls))]
