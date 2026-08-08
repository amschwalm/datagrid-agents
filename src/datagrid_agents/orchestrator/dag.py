"""DAG plan model and staged parallel execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult, run_parallel
from datagrid_agents.orchestrator.registry import load_role, load_roles


@dataclass(frozen=True)
class DagCall:
    """One agent invocation inside a stage."""

    role: str
    focus: str = ""
    chat_mode: str | None = None
    repeats: int = 1


@dataclass(frozen=True)
class DagStage:
    """A stage of parallel calls; may depend on prior stages."""

    id: str
    calls: list[DagCall]
    name: str = ""
    depends_on: list[str] = field(default_factory=list)
    include_prior: bool = True


@dataclass
class DagPlan:
    """Natural-language-composed orchestration plan."""

    goal: str
    stages: list[DagStage]
    planner: str = "heuristic"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DagPlan":
        if not isinstance(data, dict):
            raise ValueError("DAG plan must be a mapping")
        goal = str(data.get("goal") or "").strip()
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise ValueError("DAG plan requires a non-empty stages list")
        stages = [_parse_stage(item) for item in raw_stages]
        return cls(
            goal=goal,
            stages=stages,
            planner=str(data.get("planner") or "manual"),
            rationale=str(data.get("rationale") or ""),
        )


def _parse_stage(raw: Any) -> DagStage:
    if not isinstance(raw, dict):
        raise ValueError("each stage must be a mapping")
    stage_id = str(raw.get("id") or "").strip()
    if not stage_id:
        raise ValueError("stage.id is required")
    raw_calls = raw.get("calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        raise ValueError(f"stage '{stage_id}' requires a non-empty calls list")
    calls: list[DagCall] = []
    for item in raw_calls:
        if not isinstance(item, dict):
            raise ValueError(f"stage '{stage_id}': call entries must be mappings")
        role = str(item.get("role") or "").strip()
        if not role:
            raise ValueError(f"stage '{stage_id}': call.role is required")
        repeats = int(item.get("repeats") or 1)
        if repeats < 1:
            raise ValueError(f"stage '{stage_id}': repeats must be >= 1")
        chat_mode = item.get("chat_mode")
        calls.append(
            DagCall(
                role=role,
                focus=str(item.get("focus") or "").strip(),
                chat_mode=str(chat_mode).strip() if chat_mode else None,
                repeats=repeats,
            )
        )
    depends = raw.get("depends_on") or []
    if not isinstance(depends, list):
        raise ValueError(f"stage '{stage_id}': depends_on must be a list")
    include_prior = raw.get("include_prior", True)
    return DagStage(
        id=stage_id,
        calls=calls,
        name=str(raw.get("name") or stage_id),
        depends_on=[str(d) for d in depends],
        include_prior=bool(include_prior),
    )


def validate_plan(plan: DagPlan) -> None:
    """Validate roles exist and the dependency graph is a DAG."""
    known = set(load_roles())
    ids = [stage.id for stage in plan.stages]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate stage ids in DAG plan")
    id_set = set(ids)
    for stage in plan.stages:
        for dep in stage.depends_on:
            if dep not in id_set:
                raise ValueError(
                    f"stage '{stage.id}' depends on unknown stage '{dep}'"
                )
        for call in stage.calls:
            if call.role not in known:
                available = ", ".join(sorted(known))
                raise ValueError(
                    f"unknown role '{call.role}' in stage '{stage.id}'. "
                    f"Available: {available}"
                )
    # Cycle check via topological sort
    order_stages(plan)


def order_stages(plan: DagPlan) -> list[DagStage]:
    """Return stages in dependency order (Kahn)."""
    by_id = {stage.id: stage for stage in plan.stages}
    indegree = {stage.id: 0 for stage in plan.stages}
    children: dict[str, list[str]] = {stage.id: [] for stage in plan.stages}
    for stage in plan.stages:
        for dep in stage.depends_on:
            indegree[stage.id] += 1
            children[dep].append(stage.id)

    queue = sorted(stage_id for stage_id, deg in indegree.items() if deg == 0)
    ordered: list[DagStage] = []
    while queue:
        stage_id = queue.pop(0)
        ordered.append(by_id[stage_id])
        for child in sorted(children[stage_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
                queue.sort()
    if len(ordered) != len(plan.stages):
        raise ValueError("DAG plan has a dependency cycle")
    return ordered


def _build_call_prompt(
    *,
    goal: str,
    context: str,
    stage: DagStage,
    call: DagCall,
    pass_index: int,
    pass_count: int,
    prior_text: str,
) -> str:
    role = load_role(call.role)
    parts = [
        "You are one specialist node in a multi-stage Cursor/Datagrid orchestration DAG.",
        "Focus only on your specialty and the focus instructions for this node.",
        "",
        f"Stage: {stage.id}" + (f" ({stage.name})" if stage.name else ""),
        f"Role key: {role.key}",
        f"Specialty: {role.role}",
        f"Agent name: {role.name}",
    ]
    if call.focus:
        parts.extend(["", "## Node focus", call.focus])
    if pass_count > 1:
        parts.extend(
            [
                "",
                f"This is pass {pass_index} of {pass_count} for role '{call.role}'.",
                "Take a distinct angle from other passes.",
            ]
        )
    parts.extend(["", "## Overall goal", goal.strip() or "(empty)"])
    if prior_text.strip():
        parts.extend(
            [
                "",
                "## Prior stage outputs",
                "Use these as inputs; do not ignore contradictions—call them out.",
                prior_text.strip(),
            ]
        )
    if context.strip():
        parts.extend(["", context.strip()])
    parts.extend(
        [
            "",
            "## Response format",
            "1. Short framing (2-4 sentences)",
            "2. Markdown table of findings (max 8 rows)",
            "3. One recommended next action",
        ]
    )
    return "\n".join(parts)


def execute_plan(
    plan: DagPlan,
    *,
    context: str = "",
    max_workers: int = 3,
    converse: Callable[[AgentCall], Any] | None = None,
) -> tuple[list[AgentResult], list[dict[str, Any]]]:
    """Execute a validated DAG; return flat results plus stage summaries."""
    validate_plan(plan)
    stage_outputs: dict[str, list[AgentResult]] = {}
    all_results: list[AgentResult] = []
    stage_summaries: list[dict[str, Any]] = []

    for stage in order_stages(plan):
        prior_chunks: list[str] = []
        if stage.include_prior:
            for dep in stage.depends_on:
                for result in stage_outputs.get(dep, []):
                    header = f"### {dep} / {result.role}"
                    body = result.error or result.text or "(empty)"
                    prior_chunks.append(f"{header}\n{body}")
        prior_text = "\n\n".join(prior_chunks)

        calls: list[AgentCall] = []
        for call in stage.calls:
            role = load_role(call.role)
            for pass_index in range(1, call.repeats + 1):
                label = (
                    f"{stage.id}:{call.role}"
                    if call.repeats == 1
                    else f"{stage.id}:{call.role}#{pass_index}"
                )
                calls.append(
                    AgentCall(
                        role=label,
                        agent_id=role.id,
                        prompt=_build_call_prompt(
                            goal=plan.goal,
                            context=context,
                            stage=stage,
                            call=call,
                            pass_index=pass_index,
                            pass_count=call.repeats,
                            prior_text=prior_text,
                        ),
                        chat_mode=call.chat_mode or role.chat_mode,
                    )
                )

        results = run_parallel(calls, max_workers=max_workers, converse=converse)
        stage_outputs[stage.id] = results
        all_results.extend(results)
        stage_summaries.append(
            {
                "id": stage.id,
                "name": stage.name,
                "depends_on": list(stage.depends_on),
                "calls": len(calls),
                "ok": all(r.ok for r in results),
                "roles": [r.role for r in results],
            }
        )

    return all_results, stage_summaries
