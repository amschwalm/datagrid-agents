"""Flexible role fan-out for new or ad-hoc agent combinations."""

from __future__ import annotations

from datagrid_agents.orchestrator.common import build_role_calls
from datagrid_agents.orchestrator.parallel import AgentCall

WORKFLOW = "fanout"

_ACTIVE_ROLES: list[str] = []
_ACTIVE_REPEATS = 1

INSTRUCTIONS = """
You are one specialist in a multi-agent review orchestrated from Cursor.
Focus only on your specialty. Be concrete and actionable.

Respond with:
1. A short specialty framing (2-4 sentences)
2. A markdown table of the most important findings from YOUR specialty (max 8)
3. One recommended next action
""".strip()


def configure(roles: list[str], *, repeats: int = 1) -> None:
    """Configure the next fanout build_calls invocation."""
    if not roles:
        raise ValueError("fanout requires at least one role (e.g. mentor,schedule)")
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    global _ACTIVE_ROLES, _ACTIVE_REPEATS
    _ACTIVE_ROLES = list(roles)
    _ACTIVE_REPEATS = repeats


def build_calls(user_goal: str, context: str = "") -> list[AgentCall]:
    """Create calls for the configured roles (supports repeats of the same agent)."""
    if not _ACTIVE_ROLES:
        raise ValueError(
            "fanout workflow requires --roles (comma-separated orchestrator role keys)"
        )
    return build_role_calls(
        _ACTIVE_ROLES,
        instructions=INSTRUCTIONS,
        user_goal=user_goal,
        context=context,
        repeats=_ACTIVE_REPEATS,
    )
