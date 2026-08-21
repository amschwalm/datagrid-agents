"""Shared helpers for building role-based Datagrid calls."""

from __future__ import annotations

from datagrid_agents.orchestrator.parallel import AgentCall
from datagrid_agents.orchestrator.registry import load_role


def build_role_prompt(
    *,
    instructions: str,
    user_goal: str,
    context: str,
    role_key: str,
    pass_index: int = 1,
    pass_count: int = 1,
) -> str:
    """Build a specialty-scoped prompt for one agent call."""
    role = load_role(role_key)
    parts = [
        instructions.strip(),
        "",
        f"Your role key: {role.key}",
        f"Your specialty: {role.role}",
        f"Agent name: {role.name}",
    ]
    if pass_count > 1:
        parts.extend(
            [
                "",
                f"This is pass {pass_index} of {pass_count} for the same specialty.",
                "Take a distinct angle from other passes; do not merely repeat yourself.",
            ]
        )
    parts.extend(["", "## User goal", user_goal.strip()])
    if context.strip():
        parts.extend(["", context.strip()])
    return "\n".join(parts)


def build_role_calls(
    role_keys: list[str] | tuple[str, ...],
    *,
    instructions: str,
    user_goal: str,
    context: str = "",
    repeats: int = 1,
) -> list[AgentCall]:
    """Create one or more AgentCalls per role (supports calling the same agent repeatedly)."""
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    if not role_keys:
        raise ValueError("at least one role is required")

    calls: list[AgentCall] = []
    for role_key in role_keys:
        role = load_role(role_key)
        for pass_index in range(1, repeats + 1):
            label = role.key if repeats == 1 else f"{role.key}#{pass_index}"
            calls.append(
                AgentCall(
                    role=label,
                    agent_id=role.id,
                    prompt=build_role_prompt(
                        instructions=instructions,
                        user_goal=user_goal,
                        context=context,
                        role_key=role_key,
                        pass_index=pass_index,
                        pass_count=repeats,
                    ),
                    chat_mode=role.chat_mode,
                )
            )
    return calls
