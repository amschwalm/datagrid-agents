"""Load and validate local construction agent definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


@dataclass(frozen=True)
class AgentDefinition:
    """A local blueprint used to create an agent in Datagrid."""

    slug: str
    name: str
    description: str
    system_prompt: str
    custom_prompt: str | None = None
    planning_prompt: str | None = None
    agent_model: str = "magpie-2.5"
    tools: list[str] = field(default_factory=list)
    knowledge_env: str | None = None
    sample_prompt: str | None = None

    def create_params(self, knowledge_ids: list[str] | None = None) -> dict[str, Any]:
        """Build kwargs for `client.agents.create`."""
        params: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "agent_model": self.agent_model,
        }
        if self.custom_prompt:
            params["custom_prompt"] = self.custom_prompt
        if self.planning_prompt:
            params["planning_prompt"] = self.planning_prompt
        if self.tools:
            params["tools"] = self.tools
        if knowledge_ids:
            params["corpus"] = [
                {"type": "knowledge", "knowledge_id": kid} for kid in knowledge_ids
            ]
        return params


def _parse_definition(raw: dict[str, Any], slug: str) -> AgentDefinition:
    required = ("name", "description", "system_prompt")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"{slug}: missing required fields: {', '.join(missing)}")

    return AgentDefinition(
        slug=slug,
        name=str(raw["name"]),
        description=str(raw["description"]),
        system_prompt=str(raw["system_prompt"]).strip(),
        custom_prompt=_optional_str(raw.get("custom_prompt")),
        planning_prompt=_optional_str(raw.get("planning_prompt")),
        agent_model=str(raw.get("agent_model") or "magpie-2.5"),
        tools=[str(t) for t in (raw.get("tools") or [])],
        knowledge_env=_optional_str(raw.get("knowledge_env")),
        sample_prompt=_optional_str(raw.get("sample_prompt")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def list_definition_slugs() -> list[str]:
    """Return available definition slugs sorted alphabetically."""
    if not DEFINITIONS_DIR.exists():
        return []
    return sorted(path.stem for path in DEFINITIONS_DIR.glob("*.yaml"))


def load_definition(slug: str) -> AgentDefinition:
    """Load one agent definition by slug (filename without extension)."""
    path = DEFINITIONS_DIR / f"{slug}.yaml"
    if not path.exists():
        available = ", ".join(list_definition_slugs()) or "(none)"
        raise FileNotFoundError(
            f"Unknown agent definition '{slug}'. Available: {available}"
        )
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{slug}: definition must be a YAML mapping")
    return _parse_definition(raw, slug)


def list_definitions() -> list[AgentDefinition]:
    """Load all local agent definitions."""
    return [load_definition(slug) for slug in list_definition_slugs()]
