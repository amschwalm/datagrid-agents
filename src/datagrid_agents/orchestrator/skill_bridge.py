"""Import the Cursor skill's stdlib orchestrator scripts."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[3] / ".cursor" / "skills" / "datagrid-orchestrator" / "scripts"
)


def skill_scripts_dir() -> Path:
    if not SKILL_SCRIPTS.is_dir():
        raise FileNotFoundError(f"Orchestrator skill scripts not found: {SKILL_SCRIPTS}")
    return SKILL_SCRIPTS


@lru_cache(maxsize=1)
def load_skill_modules() -> tuple[ModuleType, ModuleType]:
    """Return (datagrid_client, orchestrate) modules from the skill folder."""
    scripts = skill_scripts_dir()
    path = str(scripts)
    if path not in sys.path:
        sys.path.insert(0, path)
    import datagrid_client as client_mod
    import orchestrate as orch_mod

    return client_mod, orch_mod
