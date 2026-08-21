"""Utility / electrical package buyout risk playbook."""

from __future__ import annotations

from datagrid_agents.orchestrator.common import build_role_calls
from datagrid_agents.orchestrator.parallel import AgentCall

WORKFLOW = "utility_buyout_risks"

ROLES = ("mentor", "schedule", "change_order")

INSTRUCTIONS = """
You are contributing to a multi-agent buyout risk review for an electrical /
utility package. Focus only on your specialty. Prefer concrete, field-proven
risks over generic advice. When possible, cite project patterns or lesson themes
from knowledge available to you.

Respond with:
1. A short specialty framing (2-4 sentences)
2. A markdown table of the top risks from YOUR specialty (max 5), with columns:
   Risk | Why it matters | Preventative action
3. One recommended next action for the project team
""".strip()


def build_calls(user_goal: str, context: str = "") -> list[AgentCall]:
    """Create parallel Datagrid calls for the utility buyout workflow."""
    return build_role_calls(
        ROLES,
        instructions=INSTRUCTIONS,
        user_goal=user_goal,
        context=context,
    )
