"""Execute named orchestration workflows and persist run artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from datagrid_agents.orchestrator.compose import compose_plan
from datagrid_agents.orchestrator.context import gather_context
from datagrid_agents.orchestrator.dag import DagPlan, execute_plan, validate_plan
from datagrid_agents.orchestrator.differential import analyze_attachment_coverage
from datagrid_agents.orchestrator.merge import OrchestratorRun, merge_results
from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult, run_parallel
from datagrid_agents.orchestrator.workflows import (
    DIFFERENTIAL_WORKFLOWS,
    get_workflow_builder,
    list_workflow_names,
    prepare_workflow,
)

DEFAULT_RUNS_DIR = Path.cwd() / ".orchestrator" / "runs"


def list_workflows() -> list[str]:
    """Return available workflow names."""
    return list_workflow_names()


def run_workflow(
    name: str,
    prompt: str,
    *,
    context_paths: list[Path | str] | None = None,
    roles: list[str] | None = None,
    repeats: int = 1,
    max_workers: int = 3,
    runs_dir: Path | None = DEFAULT_RUNS_DIR,
    converse: Callable[[AgentCall], Any] | None = None,
) -> OrchestratorRun:
    """Gather local context, fan out Datagrid calls, merge, optionally persist."""
    if not prompt or not str(prompt).strip():
        raise ValueError("prompt is required")

    prepare_workflow(name, roles=roles, repeats=repeats)

    context = gather_context(context_paths)
    if name in DIFFERENTIAL_WORKFLOWS:
        analysis = analyze_attachment_coverage(prompt, context_paths)
        context = (analysis + "\n" + context).strip()

    builder = get_workflow_builder(name)
    calls = builder(prompt, context)
    results: list[AgentResult] = run_parallel(
        calls, max_workers=max_workers, converse=converse
    )
    run = merge_results(
        workflow=name,
        prompt=prompt,
        results=results,
        context=context,
        title=f"Orchestrator: {name}",
    )
    if runs_dir is not None:
        _persist_run(run, Path(runs_dir))
    return run


def run_compose(
    prompt: str,
    *,
    context_paths: list[Path | str] | None = None,
    mode: str = "auto",
    planner_role: str = "mentor",
    plan: DagPlan | dict[str, Any] | None = None,
    plan_only: bool = False,
    max_workers: int = 3,
    runs_dir: Path | None = DEFAULT_RUNS_DIR,
    converse: Callable[[AgentCall], Any] | None = None,
) -> OrchestratorRun:
    """Compose a DAG from natural language (or a provided plan) and execute it."""
    if plan is None:
        if not prompt or not str(prompt).strip():
            raise ValueError("prompt is required")
        dag = compose_plan(
            prompt,
            mode=mode,
            planner_role=planner_role,
            converse=converse,
        )
    else:
        dag = plan if isinstance(plan, DagPlan) else DagPlan.from_dict(plan)
        if not dag.goal:
            dag.goal = prompt
        validate_plan(dag)

    if plan_only:
        run = OrchestratorRun(
            workflow="compose",
            prompt=dag.goal or prompt,
            created_at=datetime.now(timezone.utc).isoformat(),
            context_chars=0,
            results=[],
            markdown=_plan_markdown(dag),
            ok=True,
            plan=dag.to_dict(),
            stages=[],
        )
        if runs_dir is not None:
            _persist_run(run, Path(runs_dir), suffix="plan")
        return run

    context = gather_context(context_paths)
    # Open-ended compose benefits from the same attachment coverage signal.
    analysis = analyze_attachment_coverage(dag.goal or prompt, context_paths)
    if analysis.strip():
        context = (analysis + "\n" + context).strip()

    results, stage_summaries = execute_plan(
        dag,
        context=context,
        max_workers=max_workers,
        converse=converse,
    )
    run = merge_results(
        workflow="compose",
        prompt=dag.goal or prompt,
        results=results,
        context=context,
        title="Orchestrator: compose",
        plan=dag.to_dict(),
        stages=stage_summaries,
    )
    if runs_dir is not None:
        _persist_run(run, Path(runs_dir))
    return run


def _plan_markdown(plan: DagPlan) -> str:
    lines = [
        "# Orchestrator: compose (plan only)",
        "",
        f"- planner: `{plan.planner}`",
        f"- goal: {plan.goal}",
    ]
    if plan.rationale:
        lines.append(f"- rationale: {plan.rationale}")
    lines.extend(["", "## Stages", ""])
    for stage in plan.stages:
        deps = ", ".join(stage.depends_on) or "(none)"
        lines.append(f"### `{stage.id}` — {stage.name or stage.id}")
        lines.append(f"- depends_on: {deps}")
        lines.append(f"- include_prior: {stage.include_prior}")
        for call in stage.calls:
            focus = f" — {call.focus}" if call.focus else ""
            repeat = f" x{call.repeats}" if call.repeats > 1 else ""
            lines.append(f"- `{call.role}`{repeat}{focus}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _persist_run(
    run: OrchestratorRun,
    runs_dir: Path,
    *,
    suffix: str | None = None,
) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = (
        run.created_at.replace("+00:00", "Z")
        .replace("+0000", "Z")
        .replace(":", "")
        .replace(".", "-")
    )
    name = run.workflow if not suffix else f"{run.workflow}_{suffix}"
    base = runs_dir / f"{stamp}_{name}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(run.to_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(run.markdown, encoding="utf-8")
    return json_path
