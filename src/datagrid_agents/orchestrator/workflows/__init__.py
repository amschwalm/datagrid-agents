"""Named orchestration playbooks."""

from __future__ import annotations

from typing import Callable

from datagrid_agents.orchestrator.parallel import AgentCall
from datagrid_agents.orchestrator.workflows import fanout as fanout_workflow
from datagrid_agents.orchestrator.workflows.lessons_multipass import (
    build_calls as build_lessons_multipass,
)
from datagrid_agents.orchestrator.workflows.rfi_packet_qa import (
    build_calls as build_rfi_packet_qa,
)
from datagrid_agents.orchestrator.workflows.submittal_disposition import (
    build_calls as build_submittal_disposition,
)
from datagrid_agents.orchestrator.workflows.utility_buyout_risks import (
    build_calls as build_utility_buyout_risks,
)

WorkflowBuilder = Callable[[str, str], list[AgentCall]]

WORKFLOWS: dict[str, WorkflowBuilder] = {
    "utility_buyout_risks": build_utility_buyout_risks,
    "rfi_packet_qa": build_rfi_packet_qa,
    "submittal_disposition": build_submittal_disposition,
    "lessons_multipass": build_lessons_multipass,
    "fanout": fanout_workflow.build_calls,
}

# Workflows that benefit from local attachment/token coverage analysis.
DIFFERENTIAL_WORKFLOWS = frozenset({"rfi_packet_qa", "submittal_disposition"})


def list_workflow_names() -> list[str]:
    return sorted(WORKFLOWS)


def get_workflow_builder(name: str) -> WorkflowBuilder:
    try:
        return WORKFLOWS[name]
    except KeyError as exc:
        available = ", ".join(list_workflow_names()) or "(none)"
        raise KeyError(
            f"Unknown workflow '{name}'. Available: {available}"
        ) from exc


def prepare_workflow(
    name: str,
    *,
    roles: list[str] | None = None,
    repeats: int = 1,
) -> None:
    """Apply workflow-specific configuration before build_calls."""
    if name == "fanout":
        fanout_workflow.configure(roles or [], repeats=repeats)
        return
    if roles:
        raise ValueError(
            f"--roles is only supported for the 'fanout' workflow (got '{name}')"
        )
    if repeats != 1:
        raise ValueError(
            f"--repeat is only supported for the 'fanout' workflow (got '{name}')"
        )
