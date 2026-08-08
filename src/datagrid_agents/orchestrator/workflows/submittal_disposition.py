"""Submittal vs specification disposition playbook."""

from __future__ import annotations

from datagrid_agents.orchestrator.common import build_role_calls
from datagrid_agents.orchestrator.parallel import AgentCall

WORKFLOW = "submittal_disposition"

ROLES = ("submittal", "drawings_specs", "deep_search")

INSTRUCTIONS = """
You are contributing to a multi-agent submittal disposition review. Focus only
on your specialty. Compare the submittal package against specifications and
drawings. Call out compliance gaps, substitutions, and missing data.

Respond with:
1. A short specialty framing (2-4 sentences)
2. A markdown table of disposition items (max 8), with columns:
   Item | Disposition (approve / approve-as-noted / revise-and-resubmit / reject) | Spec/drawing basis | Notes
3. One recommended next action for the reviewer/PM
""".strip()


def build_calls(user_goal: str, context: str = "") -> list[AgentCall]:
    """Create parallel Datagrid calls for submittal disposition."""
    return build_role_calls(
        ROLES,
        instructions=INSTRUCTIONS,
        user_goal=user_goal,
        context=context,
    )
