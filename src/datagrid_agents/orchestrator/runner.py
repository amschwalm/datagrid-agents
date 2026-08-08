"""Execute named orchestration workflows and persist run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from datagrid_agents.orchestrator.context import gather_context
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


def _persist_run(run: OrchestratorRun, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = run.created_at.replace(":", "").replace("+00:00", "Z")
    base = runs_dir / f"{stamp}_{run.workflow}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(run.to_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(run.markdown, encoding="utf-8")
    return json_path
