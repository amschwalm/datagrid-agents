"""Parallel Datagrid converse calls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable

from datagrid_agents import service


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
    max_workers: int = 3,
    converse: Callable[[AgentCall], Any] | None = None,
) -> list[AgentResult]:
    """Run Datagrid agent calls concurrently; preserve input order in results."""
    if not calls:
        return []
    worker = converse or _default_converse
    workers = max(1, min(max_workers, len(calls)))
    results: dict[int, AgentResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_execute_call, call, worker): index
            for index, call in enumerate(calls)
        }
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()
    return [results[i] for i in range(len(calls))]
