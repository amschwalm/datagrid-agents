"""RFI packet completeness / clarity playbook."""

from __future__ import annotations

from datagrid_agents.orchestrator.common import build_role_calls
from datagrid_agents.orchestrator.parallel import AgentCall

WORKFLOW = "rfi_packet_qa"

# deep_search covers RFI/project docs; drawings_specs + drawing_revision add sheet focus.
# Point DATAGRID_AGENT_RFI at a dedicated RFI agent when you build one, then add `rfi`
# to ROLES (and agents.yaml) without changing the workflow shape.
ROLES = ("deep_search", "drawings_specs", "drawing_revision")

INSTRUCTIONS = """
You are contributing to a multi-agent RFI packet QA review. Focus only on your
specialty. Check completeness, clarity, drawing/spec references, and missing
attachments. Prefer concrete findings over generic process advice.

Respond with:
1. A short specialty framing (2-4 sentences)
2. A markdown table of findings (max 8), with columns:
   Finding | Severity (high/med/low) | Evidence / reference | Recommended fix
3. One recommended next action before the RFI is issued
""".strip()


def build_calls(user_goal: str, context: str = "") -> list[AgentCall]:
    """Create parallel Datagrid calls for RFI packet QA."""
    return build_role_calls(
        ROLES,
        instructions=INSTRUCTIONS,
        user_goal=user_goal,
        context=context,
    )
