"""Create, sync, list, and run construction agents via the Datagrid API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from datagrid_agents.client import get_client
from datagrid_agents.registry import AgentDefinition, list_definitions, load_definition

DEFAULT_STATE_PATH = Path.cwd() / ".agent_ids.json"


def knowledge_ids_for(definition: AgentDefinition) -> list[str]:
    """Resolve optional knowledge IDs from the definition's env var."""
    env_name = definition.knowledge_env or "CONSTRUCTION_KNOWLEDGE_IDS"
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, str]:
    """Load slug -> agent_id mapping written by create/sync commands."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid agent state file: {path}")
    return {str(k): str(v) for k, v in data.items()}


def save_state(state: dict[str, str], path: Path = DEFAULT_STATE_PATH) -> None:
    """Persist slug -> agent_id mapping."""
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_agent(
    definition: AgentDefinition,
    *,
    knowledge_ids: list[str] | None = None,
) -> Any:
    """Create a Datagrid agent from a local definition."""
    client = get_client()
    ids = knowledge_ids if knowledge_ids is not None else knowledge_ids_for(definition)
    return client.agents.create(**definition.create_params(ids))


def create_all(
    *,
    slugs: list[str] | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    """Create selected (or all) local agents and update the local ID map."""
    selected = (
        [load_definition(slug) for slug in slugs]
        if slugs
        else list_definitions()
    )
    state = load_state(state_path)
    created: dict[str, Any] = {}
    for definition in selected:
        agent = create_agent(definition)
        state[definition.slug] = agent.id
        created[definition.slug] = agent
    save_state(state, state_path)
    return created


def find_remote_agent_id_by_name(name: str) -> str | None:
    """Return the first remote agent ID whose name exactly matches."""
    client = get_client()
    for agent in client.agents.list(search=name):
        if agent.name == name:
            return agent.id
    return None


def sync_agent(
    definition: AgentDefinition,
    *,
    agent_id: str | None = None,
    knowledge_ids: list[str] | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> Any:
    """Update an existing agent, or create it if no ID is known."""
    client = get_client()
    state = load_state(state_path)
    resolved_id = agent_id or state.get(definition.slug) or find_remote_agent_id_by_name(
        definition.name
    )
    ids = knowledge_ids if knowledge_ids is not None else knowledge_ids_for(definition)
    params = definition.create_params(ids)

    if resolved_id:
        agent = client.agents.update(resolved_id, **params)
    else:
        agent = client.agents.create(**params)

    state[definition.slug] = agent.id
    save_state(state, state_path)
    return agent


def sync_all(
    *,
    slugs: list[str] | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    """Create-or-update selected (or all) local agent definitions."""
    selected = (
        [load_definition(slug) for slug in slugs]
        if slugs
        else list_definitions()
    )
    synced: dict[str, Any] = {}
    for definition in selected:
        synced[definition.slug] = sync_agent(definition, state_path=state_path)
    return synced


def resolve_agent_id(slug_or_id: str, state_path: Path = DEFAULT_STATE_PATH) -> str:
    """Accept a slug from local state or a raw Datagrid agent ID."""
    state = load_state(state_path)
    if slug_or_id in state:
        return state[slug_or_id]
    if slug_or_id.startswith("agent_") or len(slug_or_id) > 20:
        return slug_or_id
    available = ", ".join(sorted(state)) or "(none — run create/sync first)"
    raise KeyError(
        f"No agent ID for '{slug_or_id}'. Known slugs: {available}"
    )


def list_remote_agents(search: str | None = None) -> list[Any]:
    """List agents from the authenticated Datagrid organization."""
    client = get_client()
    kwargs: dict[str, Any] = {}
    if search:
        kwargs["search"] = search
    return list(client.agents.list(**kwargs))


def converse_with_agent(
    slug_or_id: str,
    prompt: str,
    *,
    chat_mode: str = "full_agent",
    conversation_id: str | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> Any:
    """Run a prompt against a created agent."""
    client = get_client()
    agent_id = resolve_agent_id(slug_or_id, state_path=state_path)
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "agent_id": agent_id,
        "chat_mode": chat_mode,
    }
    if conversation_id:
        kwargs["conversation_id"] = conversation_id
    return client.converse(**kwargs)


def response_text(response: Any) -> str:
    """Best-effort extraction of text from a Converse response."""
    content = getattr(response, "content", None) or []
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
            continue
        if isinstance(item, dict) and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def response_credits(response: Any) -> float | None:
    """Best-effort extraction of credits.consumed from a Converse response."""
    credits = getattr(response, "credits", None)
    if credits is None and isinstance(response, dict):
        credits = response.get("credits")
    if credits is None:
        return None
    consumed = getattr(credits, "consumed", None)
    if consumed is None and isinstance(credits, dict):
        consumed = credits.get("consumed")
    if consumed is None:
        return None
    try:
        return float(consumed)
    except (TypeError, ValueError):
        return None
