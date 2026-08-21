"""Merge parallel Datagrid results with local context into one artifact."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from datagrid_agents.orchestrator.parallel import AgentResult
from datagrid_agents.orchestrator.synthesize import Synthesis, synthesize_results


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
    plan: dict[str, Any] | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] | None = None
    register_markdown: str = ""
    artifact_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def merge_results(
    *,
    workflow: str,
    prompt: str,
    results: list[AgentResult],
    context: str = "",
    title: str | None = None,
    plan: dict[str, Any] | None = None,
    stages: list[dict[str, Any]] | None = None,
    synthesize: bool = True,
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
    if plan:
        sections.extend(
            [
                "## Composed DAG",
                "",
                f"- planner: `{plan.get('planner', 'unknown')}`",
            ]
        )
        if plan.get("rationale"):
            sections.append(f"- rationale: {plan['rationale']}")
        for stage in plan.get("stages") or []:
            deps = ", ".join(stage.get("depends_on") or []) or "(none)"
            roles = ", ".join(
                call.get("role", "?") for call in (stage.get("calls") or [])
            )
            sections.append(
                f"- stage `{stage.get('id')}` deps=[{deps}] roles=[{roles}]"
            )
        sections.append("")

    if stages:
        sections.extend(["## Stage execution", ""])
        for stage in stages:
            status = "ok" if stage.get("ok") else "failed"
            cached = stage.get("cached")
            cache_note = f"; cached={cached}" if cached else ""
            sections.append(
                f"- `{stage.get('id')}` {status}; roles: "
                + ", ".join(stage.get("roles") or [])
                + cache_note
            )
        sections.append("")

    synthesis_obj: Synthesis | None = None
    register_markdown = ""
    if synthesize:
        synthesis_obj = synthesize_results(
            results, prompt=prompt, workflow=workflow
        )
        register_markdown = synthesis_obj.markdown
        sections.extend(
            [
                "## Synthesized register",
                "",
                f"{len(synthesis_obj.items)} deduped items extracted from agent tables.",
                "",
            ]
        )

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
                "cached": result.cached,
            }
        )
        sections.append(f"## Agent: {result.role}")
        sections.append("")
        sections.append(f"- agent_id: `{result.agent_id}`")
        if result.cached:
            sections.append("- cache: hit")
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
            "- Cursor owns parallelism, budgets/cache, local code context, DAG composition, synthesis, and follow-on repo operations.",
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
        plan=plan,
        stages=list(stages or []),
        synthesis=synthesis_obj.to_dict() if synthesis_obj else None,
        register_markdown=register_markdown,
    )
