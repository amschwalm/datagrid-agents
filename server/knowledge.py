"""Datagrid knowledge lookup helpers for project confirmation."""

from __future__ import annotations

import re
from typing import Any, Callable


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 1}


def score_knowledge_match(project: str, knowledge_name: str) -> float:
    """Return 0..1 similarity score between a project query and knowledge name."""
    p = _normalize(project)
    n = _normalize(knowledge_name)
    if not p or not n:
        return 0.0
    if p == n:
        return 1.0
    if p in n or n in p:
        return 0.92
    pt, nt = _tokens(p), _tokens(n)
    if not pt or not nt:
        return 0.0
    overlap = len(pt & nt) / len(pt | nt)
    # Boost if all project tokens appear in the knowledge name.
    if pt <= nt:
        overlap = max(overlap, 0.8)
    return round(overlap, 3)


def rank_knowledge_matches(
    project: str,
    items: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in items:
        score = score_knowledge_match(project, str(item.get("name") or ""))
        if score <= 0:
            continue
        ranked.append({**item, "score": score})
    ranked.sort(key=lambda row: (-float(row["score"]), str(row.get("name") or "")))
    return ranked[:limit]


def list_knowledge_catalog(
    *,
    list_page: Callable[..., Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch knowledge entries from Datagrid (injectable for tests)."""
    if list_page is None:
        from datagrid_agents.client import get_client

        client = get_client()
        list_page = client.knowledge.list

    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"limit": min(limit, 100)}
        if cursor:
            kwargs["after"] = cursor
        page = list_page(**kwargs)
        batch = list(page or [])
        if not batch:
            break
        for entry in batch:
            items.append(
                {
                    "id": getattr(entry, "id", None) or (entry.get("id") if isinstance(entry, dict) else None),
                    "name": getattr(entry, "name", None)
                    or (entry.get("name") if isinstance(entry, dict) else None)
                    or "",
                    "status": getattr(entry, "status", None)
                    or (entry.get("status") if isinstance(entry, dict) else None)
                    or "",
                    "scope": getattr(entry, "scope", None)
                    or (entry.get("scope") if isinstance(entry, dict) else None)
                    or "",
                }
            )
        # Cursor pagination: SyncCursorIDPage may expose next cursor via last id.
        if len(batch) < kwargs["limit"]:
            break
        last = batch[-1]
        cursor = getattr(last, "id", None) or (last.get("id") if isinstance(last, dict) else None)
        if not cursor or len(items) >= 300:
            break
    return [item for item in items if item.get("id") and item.get("name")]


def build_confirm_prompt(project: str, catalog: list[dict[str, Any]], ranked: list[dict[str, Any]]) -> str:
    catalog_lines = "\n".join(
        f"- {item['name']} (id={item['id']}, status={item.get('status') or 'unknown'})"
        for item in catalog[:80]
    ) or "(no knowledge entries returned)"
    ranked_lines = "\n".join(
        f"- {item['name']} (id={item['id']}, score={item['score']})"
        for item in ranked[:8]
    ) or "(no local name matches)"
    return f"""
You are confirming Datagrid knowledge access before a lessons-learned extraction.

## Project requested by user
{project.strip()}

## Knowledge catalog available to this workspace
{catalog_lines}

## Local name-match shortlist
{ranked_lines}

## Task
Decide whether the requested project is represented in Datagrid knowledge.
Prefer an exact or strong name match. If multiple candidates exist, pick the best one.
If nothing plausible exists, matched=false.

Return ONLY valid JSON:
{{
  "matched": true,
  "knowledge_id": "kn_...",
  "knowledge_name": "Project Name",
  "confidence": "high|med|low",
  "rationale": "1-2 sentences explaining the match decision",
  "alternatives": [{{"id":"kn_...","name":"..."}}],
  "reasoning_steps": [
    {{"id":"scan","label":"...","status":"done","detail":"..."}},
    {{"id":"match","label":"...","status":"done","detail":"..."}}
  ]
}}
""".strip()


def parse_confirm_payload(data: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
    matched = bool(data.get("matched"))
    knowledge_id = str(data.get("knowledge_id") or "").strip() or None
    knowledge_name = str(data.get("knowledge_name") or "").strip() or None
    confidence = str(data.get("confidence") or "med").strip().lower()
    if confidence not in {"high", "med", "low"}:
        confidence = "med"
    rationale = str(data.get("rationale") or "").strip()
    alternatives = data.get("alternatives") if isinstance(data.get("alternatives"), list) else []
    clean_alts = []
    for alt in alternatives:
        if isinstance(alt, dict) and alt.get("id") and alt.get("name"):
            clean_alts.append({"id": str(alt["id"]), "name": str(alt["name"])})

    # Fall back to best local rank if model omitted ids.
    if matched and (not knowledge_id or not knowledge_name) and ranked:
        knowledge_id = str(ranked[0]["id"])
        knowledge_name = str(ranked[0]["name"])
        confidence = "high" if float(ranked[0]["score"]) >= 0.9 else confidence

    if not matched and ranked and float(ranked[0]["score"]) >= 0.8:
        matched = True
        knowledge_id = str(ranked[0]["id"])
        knowledge_name = str(ranked[0]["name"])
        confidence = "med"
        rationale = rationale or f'Closest knowledge match is "{knowledge_name}".'

    steps = data.get("reasoning_steps") if isinstance(data.get("reasoning_steps"), list) else []
    reasoning = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        reasoning.append(
            {
                "id": str(step.get("id") or f"step-{len(reasoning)+1}"),
                "label": str(step.get("label") or "Working").strip(),
                "status": str(step.get("status") or "done"),
                "detail": str(step.get("detail") or "").strip(),
            }
        )

    return {
        "matched": matched,
        "knowledge_id": knowledge_id,
        "knowledge_name": knowledge_name,
        "confidence": confidence,
        "rationale": rationale,
        "alternatives": clean_alts[:5],
        "reasoning": reasoning,
        "candidates": ranked[:5],
    }
