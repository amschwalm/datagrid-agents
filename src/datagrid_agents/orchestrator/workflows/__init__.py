"""Workflows that still share the stdlib orchestrator (web extract pipeline)."""

from datagrid_agents.orchestrator.workflows.lessons_multipass import (
    ANALYSIS_LENSES,
    ANALYSIS_PASSES,
    build_calls,
    build_pass_calls,
)

__all__ = [
    "ANALYSIS_LENSES",
    "ANALYSIS_PASSES",
    "build_calls",
    "build_pass_calls",
]
