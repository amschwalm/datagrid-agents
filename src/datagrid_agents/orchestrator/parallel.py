"""Parallel Datagrid converse calls with budgets, timeouts, and cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from concurrent.futures import as_completed
from dataclasses import dataclass
from typing import Any, Callable

from datagrid_agents import service
from datagrid_agents.orchestrator.budget import OrchestratorBudget
from datagrid_agents.orchestrator.cache import ResultCache

# Fired as each call finishes (including cache hits). Index matches `calls`.
OnResultCallback = Callable[[int, "AgentCall", "AgentResult"], None]


@dataclass(frozen=True)
class AgentCall:
    """One Datagrid converse request."""

    role: str
    agent_id: str
    prompt: str
    chat_mode: str = "full_agent"
    conversation_id: str | None = None


@dataclass(frozen=True)
class AgentResult:
    """Outcome of one Datagrid converse request."""

    role: str
    agent_id: str
    text: str
    conversation_id: str | None = None
    error: str | None = None
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


def _default_converse(call: AgentCall) -> Any:
    return service.converse_with_agent(
        call.agent_id,
        call.prompt,
        chat_mode=call.chat_mode,
        conversation_id=call.conversation_id,
    )


def _execute_call(
    call: AgentCall,
    converse: Callable[[AgentCall], Any],
) -> AgentResult:
    try:
        response = converse(call)
        return AgentResult(
            role=call.role,
            agent_id=call.agent_id,
            text=service.response_text(response),
            conversation_id=getattr(response, "conversation_id", None),
        )
    except Exception as exc:  # noqa: BLE001 - surface per-agent failures
        return AgentResult(
            role=call.role,
            agent_id=call.agent_id,
            text="",
            error=f"{type(exc).__name__}: {exc}",
        )


def run_parallel(
    calls: list[AgentCall],
    *,
    max_workers: int | None = None,
    timeout_seconds: float | None = None,
    max_calls: int | None = None,
    budget: OrchestratorBudget | None = None,
    cache: ResultCache | bool | None = True,
    converse: Callable[[AgentCall], Any] | None = None,
    on_result: OnResultCallback | None = None,
) -> list[AgentResult]:
    """Run Datagrid agent calls concurrently; preserve input order in results."""
    if not calls:
        return []

    base = budget or OrchestratorBudget.from_env()
    workers = base.max_workers if max_workers is None else max_workers
    timeout = base.timeout_seconds if timeout_seconds is None else timeout_seconds
    call_budget = base.max_calls if max_calls is None else max_calls

    if len(calls) > call_budget:
        raise ValueError(
            f"refusing to run {len(calls)} calls; max_calls budget is {call_budget}"
        )

    result_cache: ResultCache | None
    if cache is False or cache is None:
        result_cache = None
    elif cache is True:
        result_cache = ResultCache()
    else:
        result_cache = cache

    worker = converse or _default_converse
    workers = max(1, min(workers, len(calls)))
    results: dict[int, AgentResult] = {}
    pending: dict[Any, int] = {}

    def _store(index: int, result: AgentResult) -> None:
        results[index] = result
        if on_result is not None:
            on_result(index, calls[index], result)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, call in enumerate(calls):
            if result_cache is not None:
                cached = result_cache.get(call)
                if cached is not None:
                    _store(
                        index,
                        AgentResult(
                            role=call.role,
                            agent_id=cached.agent_id,
                            text=cached.text,
                            conversation_id=cached.conversation_id,
                            error=cached.error,
                            cached=True,
                        ),
                    )
                    continue
            future = pool.submit(_execute_call, call, worker)
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
                if result_cache is not None and result.ok:
                    result_cache.put(calls[index], result)
        except FuturesTimeoutError:
            # Overall wait timed out: mark unfinished futures.
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
