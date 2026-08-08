"""Lessons-learned multipass extraction via orchestrator fan-out."""

from __future__ import annotations

from datagrid_agents.orchestrator.parallel import AgentCall
from datagrid_agents.orchestrator.registry import load_role

# Keep lens definitions colocated with the workflow so CLI + web share one source.
ANALYSIS_PASSES = 20
ROLE_KEY = "lessons_extractor"

ANALYSIS_LENSES: list[dict[str, str]] = [
    {
        "id": "cost",
        "title": "Cost & contingency",
        "focus": "cost growth, contingency burn, extras, buyout gaps, and money left on the table",
        "links": "Buyout,Change Events,RFIs",
    },
    {
        "id": "schedule",
        "title": "Schedule & sequencing",
        "focus": "logic ties, float burn, shutdown windows, trade stacking, and recovery options",
        "links": "Schedule,Meetings,Change Events",
    },
    {
        "id": "procurement",
        "title": "Procurement & buyout",
        "focus": "package strategy, vendor commitment, long-lead risk, and scope gaps at buyout",
        "links": "Buyout,Submittals,Schedule",
    },
    {
        "id": "design_rfi",
        "title": "Design coordination & RFIs",
        "focus": "drawing conflicts, RFI latency, incomplete design, and late clarifications",
        "links": "RFIs,Specs,As-Builts",
    },
    {
        "id": "change",
        "title": "Change management",
        "focus": "change events, entitlement, pricing discipline, and owner direction timing",
        "links": "Change Events,Meetings,RFIs",
    },
    {
        "id": "safety",
        "title": "Safety & field risk",
        "focus": "unsafe conditions, near misses, logistics conflicts, and field readiness",
        "links": "Daily Reports,Meetings,Schedule",
    },
    {
        "id": "quality",
        "title": "Quality & rework",
        "focus": "rework drivers, inspection failures, installation standards, and punch trends",
        "links": "Punchlist,Submittals,Daily Reports",
    },
    {
        "id": "owner",
        "title": "Owner decisions & approvals",
        "focus": "decision latency, ambiguous direction, approval bottlenecks, and scope creep",
        "links": "Meetings,Change Events,RFIs",
    },
    {
        "id": "trades",
        "title": "Trade coordination",
        "focus": "handoffs between trades, access conflicts, and multi-trade workface issues",
        "links": "Meetings,Schedule,Daily Reports",
    },
    {
        "id": "utilities",
        "title": "Utilities & site logistics",
        "focus": "utility coordination, shutdowns, laydown, access, and site constraint surprises",
        "links": "Schedule,Meetings,As-Builts",
    },
    {
        "id": "contract",
        "title": "Contracts & risk allocation",
        "focus": "contract gaps, notice failures, risk ownership, and commercial exposure",
        "links": "Change Events,RFIs,Meetings",
    },
    {
        "id": "comms",
        "title": "Communication & meetings",
        "focus": "who knew what when, meeting effectiveness, and information that never landed",
        "links": "Meetings,RFIs,Daily Reports",
    },
    {
        "id": "docs",
        "title": "Documentation & as-builts",
        "focus": "as-built accuracy, document control, and truth vs field conditions",
        "links": "As-Builts,Specs,RFIs",
    },
    {
        "id": "closeout",
        "title": "Closeout & turnover",
        "focus": "closeout package gaps, O&M readiness, commissioning, and turnover friction",
        "links": "Punchlist,Submittals,As-Builts",
    },
    {
        "id": "staffing",
        "title": "Labor & staffing",
        "focus": "crew availability, supervision bandwidth, and skill mismatches",
        "links": "Daily Reports,Schedule,Meetings",
    },
    {
        "id": "field",
        "title": "Field conditions",
        "focus": "unforeseen conditions, weather, access, and site reality vs plan",
        "links": "Daily Reports,Change Events,As-Builts",
    },
    {
        "id": "permitting",
        "title": "Permitting & AHJ",
        "focus": "inspection timing, code interpretations, and authority-having-jurisdiction friction",
        "links": "Submittals,Meetings,Schedule",
    },
    {
        "id": "bim",
        "title": "BIM & technology",
        "focus": "model coordination gaps, clash detection misses, and digital-to-field translation",
        "links": "RFIs,Specs,As-Builts",
    },
    {
        "id": "stakeholders",
        "title": "Stakeholder politics",
        "focus": "competing incentives, escalation paths, and decisions distorted by politics",
        "links": "Meetings,Change Events,RFIs",
    },
    {
        "id": "memory",
        "title": "Institutional memory",
        "focus": "repeatable process failures, what the org should bake into standards next time",
        "links": "Meetings,Specs,Punchlist",
    },
]


def build_analysis_prompt(
    lens: dict[str, str],
    prompt: str,
    interview: str,
    *,
    project: str = "",
    knowledge_name: str = "",
) -> str:
    project_block = project.strip() or "(unspecified)"
    knowledge_block = knowledge_name.strip() or "(workspace knowledge)"
    return f"""
You are running one specialized pass of a multi-pass lessons-learned extraction
against Datagrid project knowledge.

## Project
{project_block}

## Knowledge source
{knowledge_block}

## Lens
{lens["title"]} — focus on {lens["focus"]}.

## Extraction brief
{prompt}

## Scope guidance from the user
{interview}

## Task
Extract 4 to 8 concrete findings through THIS lens only.
Prioritize buried, non-obvious signals that require joining multiple artifact types
(RFIs, meetings, change events, submittals, specs, daily reports, buyout, schedule,
punchlist, as-builts). Prefer correlative evidence over generic advice.
When possible, name the cross-links that make the lesson hard to spot in one place.

Return ONLY valid JSON:
{{
  "lens": "{lens["id"]}",
  "summary": "2-3 sentences on what this lens uncovered across sources",
  "reasoning": "1-2 sentences describing the correlative path you followed",
  "findings": [
    {{
      "finding": "short title",
      "category": "category label",
      "evidence": "what across the knowledge supports this (cite artifact types)",
      "recommendation": "what to do differently",
      "priority": "high|med|low",
      "artifacts": ["RFIs", "Meetings"],
      "correlation": "why this is easy to miss if sources are read in isolation"
    }}
  ]
}}
""".strip()


def build_pass_calls(
    prompt: str,
    interview: str = "",
    *,
    role_key: str = ROLE_KEY,
    lenses: list[dict[str, str]] | None = None,
    project: str = "",
    knowledge_name: str = "",
) -> list[AgentCall]:
    """Build one orchestrator AgentCall per analysis lens."""
    role = load_role(role_key)
    selected = list(lenses or ANALYSIS_LENSES[:ANALYSIS_PASSES])
    calls: list[AgentCall] = []
    for lens in selected:
        calls.append(
            AgentCall(
                role=f"{role_key}:{lens['id']}",
                agent_id=role.id,
                prompt=build_analysis_prompt(
                    lens,
                    prompt,
                    interview or "(none)",
                    project=project,
                    knowledge_name=knowledge_name,
                ),
                chat_mode=role.chat_mode or "full_agent",
            )
        )
    return calls


def build_calls(user_goal: str, context: str = "") -> list[AgentCall]:
    """CLI/orchestrator entry: treat context as the interview brief."""
    return build_pass_calls(user_goal, context)
