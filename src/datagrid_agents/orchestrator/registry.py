"""Load Datagrid agent roles used by the orchestrator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

AGENTS_PATH = Path(__file__).resolve().parent / "agents.yaml"


@dataclass(frozen=True)
class AgentRole:
    """A named Datagrid agent available for orchestration."""

    key: str
    id: str
    name: str
    role: str
    chat_mode: str = "full_agent"
    description: str = ""


def _optional_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _env_override_key(role_key: str) -> str:
    return f"DATAGRID_AGENT_{role_key.upper()}"


def _parse_role(key: str, raw: dict[str, Any]) -> AgentRole:
    agent_id = _optional_str(os.environ.get(_env_override_key(key))) or _optional_str(
        raw.get("id")
    )
    if not agent_id:
        raise ValueError(f"{key}: missing Datagrid agent id")
    name = _optional_str(raw.get("name")) or key
    role = _optional_str(raw.get("role")) or key
    chat_mode = _optional_str(raw.get("chat_mode")) or "full_agent"
    description = _optional_str(raw.get("description"))
    return AgentRole(
        key=key,
        id=agent_id,
        name=name,
        role=role,
        chat_mode=chat_mode,
        description=description,
    )


def load_roles(path: Path | None = None) -> dict[str, AgentRole]:
    """Load all orchestrator agent roles from YAML."""
    roles_path = path or AGENTS_PATH
    if not roles_path.exists():
        raise FileNotFoundError(f"Agent registry not found: {roles_path}")
    with roles_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("agents.yaml must be a mapping of role key -> config")
    roles: dict[str, AgentRole] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"{key}: role config must be a mapping")
        roles[str(key)] = _parse_role(str(key), value)
    return roles


def list_roles(path: Path | None = None) -> list[AgentRole]:
    """Return roles sorted by key."""
    roles = load_roles(path)
    return [roles[key] for key in sorted(roles)]


def load_role(key: str, path: Path | None = None) -> AgentRole:
    """Load one role by key."""
    roles = load_roles(path)
    if key not in roles:
        available = ", ".join(sorted(roles)) or "(none)"
        raise KeyError(f"Unknown orchestrator role '{key}'. Available: {available}")
    return roles[key]
