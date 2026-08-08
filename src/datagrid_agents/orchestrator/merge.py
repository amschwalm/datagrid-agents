"""Merge parallel Datagrid results with local context into one artifact."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from datagrid_agents.orchestrator.parallel import AgentResult


@dataclass
class OrchestratorRun:
    """Structured output of one orchestration workflow."""

    workflow: str
    prompt: str
    created_at: str
    context_chars: int
    results: list[dict[str, Any]] = field(default_factory=list)
    markdown: str = ""
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def merge_results(
    *,
    workflow: str,
    prompt: str,
    results: list[AgentResult],
    context: str = "",
    title: str | None = None,
) -> OrchestratorRun:
    """Combine agent answers into markdown + JSON-friendly payload."""
    created_at = datetime.now(timezone.utc).isoformat()
    heading = title or f"Orchestrator: {workflow}"
    sections = [
        f"# {heading}",
        "",
        f"_Generated {created_at}_",
        "",
        "## User goal",
        "",
        prompt.strip() or "(empty)",
        "",
    ]
    if context.strip():
        sections.extend(
            [
                "## Local context attached",
                "",
                f"{len(context)} characters of repository context were provided to agents.",
                "",
            ]
        )

    payload_results: list[dict[str, Any]] = []
    ok = True
    for result in results:
        ok = ok and result.ok
        payload_results.append(
            {
                "role": result.role,
                "agent_id": result.agent_id,
                "conversation_id": result.conversation_id,
                "error": result.error,
                "text": result.text,
            }
        )
        sections.append(f"## Agent: {result.role}")
        sections.append("")
        sections.append(f"- agent_id: `{result.agent_id}`")
        if result.conversation_id:
            sections.append(f"- conversation_id: `{result.conversation_id}`")
        if result.error:
            sections.append(f"- error: `{result.error}`")
            sections.append("")
            sections.append("Call failed.")
        else:
            sections.append("")
            sections.append(result.text.strip() or "(empty response)")
        sections.append("")

    sections.extend(
        [
            "## Orchestrator notes",
            "",
            "- Datagrid agents supplied domain judgment / knowledge search.",
            "- Cursor owns parallelism, local code context, and follow-on repo operations.",
            "",
        ]
    )

    return OrchestratorRun(
        workflow=workflow,
        prompt=prompt,
        created_at=created_at,
        context_chars=len(context),
        results=payload_results,
        markdown="\n".join(sections).rstrip() + "\n",
        ok=ok,
    )
