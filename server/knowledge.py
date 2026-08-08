"""Datagrid project confirmation via deep search + knowledge helpers."""

from __future__ import annotations

import re
from typing import Any, Callable

UPLOAD_GUIDANCE = (
    "Upload this project's data to Datagrid (docs, RFIs, meetings, schedule, etc.), "
    "wait for knowledge indexing to finish, then come back and try again."
)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 1}


def score_knowledge_match(project: str, knowledge_name: str) -> float:
    """Return 0..1 similarity score between a project query and a name."""
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
                    "id": getattr(entry, "id", None)
                    or (entry.get("id") if isinstance(entry, dict) else None),
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
        if len(batch) < kwargs["limit"]:
            break
        last = batch[-1]
        cursor = getattr(last, "id", None) or (last.get("id") if isinstance(last, dict) else None)
        if not cursor or len(items) >= 300:
            break
    return [item for item in items if item.get("id") and item.get("name")]


def build_deep_search_confirm_prompt(
    project: str,
    catalog: list[dict[str, Any]] | None = None,
) -> str:
    catalog = catalog or []
    catalog_lines = "\n".join(
        f"- {item['name']} (id={item['id']}, status={item.get('status') or 'unknown'})"
        for item in catalog[:80]
    ) or "(knowledge catalog unavailable — rely only on document search)"
    return f"""
You are the Deep Search agent. Confirm whether the user-requested project exists
in the Datagrid data you can access BEFORE a lessons-learned extraction starts.

## User-requested project
{project.strip()}

## Knowledge catalog names (secondary hint only)
{catalog_lines}

## What to do
1. Search the files/documents/knowledge available to you for project names,
   job names, contract titles, site names, and similar identifiers.
2. Compare the user's request to the project names found IN THE FILES
   (not only the knowledge catalog labels).
3. Decide match quality:
   - exact: clear same project
   - fuzzy: close / partial / likely same project under a different label
   - none: not found in accessible data
4. If matched, return the canonical project name as it appears in the files.
5. If not matched (or fuzzy with doubt), list the distinct projects you DO have
   access to based on the documents.
6. If none, tell the user to upload their project data to Datagrid and come back.

Return ONLY valid JSON:
{{
  "matched": true,
  "match_kind": "exact|fuzzy|none",
  "project_name": "canonical project name from files",
  "knowledge_id": "kn_... or null",
  "knowledge_name": "knowledge source name if known",
  "confidence": "high|med|low",
  "rationale": "1-3 sentences on how you matched against file evidence",
  "evidence": ["short evidence notes from docs"],
  "accessible_projects": [
    {{"name":"Project A","notes":"seen in RFIs / specs","knowledge_id":null,"knowledge_name":null}}
  ],
  "upload_required": false,
  "next_step": "what the user should do next",
  "reasoning_steps": [
    {{"id":"search","label":"Searching project documents","status":"done","detail":"..."}},
    {{"id":"match","label":"Comparing names","status":"done","detail":"..."}}
  ]
}}
""".strip()


def _clean_project_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            row = {"name": name, "notes": "", "knowledge_id": None, "knowledge_name": None}
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("project_name") or "").strip()
            if not name:
                continue
            row = {
                "name": name,
                "notes": str(item.get("notes") or item.get("detail") or "").strip(),
                "knowledge_id": str(item["knowledge_id"]).strip()
                if item.get("knowledge_id")
                else None,
                "knowledge_name": str(item["knowledge_name"]).strip()
                if item.get("knowledge_name")
                else None,
            }
        else:
            continue
        key = _normalize(row["name"])
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:12]


def _attach_catalog_ids(
    rows: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not catalog:
        return rows
    enriched: list[dict[str, Any]] = []
    for row in rows:
        if row.get("knowledge_id"):
            enriched.append(row)
            continue
        ranked = rank_knowledge_matches(row["name"], catalog, limit=1)
        if ranked and float(ranked[0]["score"]) >= 0.7:
            enriched.append(
                {
                    **row,
                    "knowledge_id": ranked[0]["id"],
                    "knowledge_name": ranked[0]["name"],
                    "score": ranked[0]["score"],
                }
            )
        else:
            enriched.append(row)
    return enriched


def parse_confirm_payload(
    data: dict[str, Any],
    *,
    catalog: list[dict[str, Any]] | None = None,
    ranked: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = catalog or []
    ranked = ranked or []

    match_kind = str(data.get("match_kind") or "").strip().lower()
    if match_kind not in {"exact", "fuzzy", "none"}:
        # Infer from legacy fields.
        if data.get("matched") is False:
            match_kind = "none"
        elif str(data.get("confidence") or "").lower() == "high":
            match_kind = "exact"
        elif data.get("matched"):
            match_kind = "fuzzy"
        else:
            match_kind = "none"

    matched = bool(data.get("matched")) if "matched" in data else match_kind in {"exact", "fuzzy"}
    if match_kind == "none":
        matched = False

    confidence = str(data.get("confidence") or "med").strip().lower()
    if confidence not in {"high", "med", "low"}:
        confidence = "med"
    if match_kind == "exact" and confidence == "med":
        confidence = "high"
    if match_kind == "none":
        confidence = "low"

    project_name = (
        str(data.get("project_name") or data.get("knowledge_name") or "").strip() or None
    )
    knowledge_name = str(data.get("knowledge_name") or "").strip() or project_name
    knowledge_id = str(data.get("knowledge_id") or "").strip() or None

    # Fill knowledge id from catalog when possible.
    if matched and project_name and not knowledge_id and catalog:
        local = rank_knowledge_matches(project_name, catalog, limit=1)
        if local and float(local[0]["score"]) >= 0.7:
            knowledge_id = str(local[0]["id"])
            knowledge_name = knowledge_name or str(local[0]["name"])

    if matched and (not project_name) and ranked:
        project_name = str(ranked[0]["name"])
        knowledge_id = knowledge_id or str(ranked[0]["id"])
        knowledge_name = knowledge_name or project_name
        match_kind = "exact" if float(ranked[0]["score"]) >= 0.9 else "fuzzy"

    accessible = _attach_catalog_ids(
        _clean_project_rows(data.get("accessible_projects")),
        catalog,
    )
    # Also expose catalog names if deep search omitted them on a miss.
    if not matched and not accessible and catalog:
        accessible = [
            {
                "name": item["name"],
                "notes": f"Knowledge source ({item.get('status') or 'unknown'})",
                "knowledge_id": item["id"],
                "knowledge_name": item["name"],
            }
            for item in catalog[:12]
        ]

    rationale = str(data.get("rationale") or "").strip()
    evidence = data.get("evidence") if isinstance(data.get("evidence"), list) else []
    evidence_clean = [str(e).strip() for e in evidence if str(e).strip()][:8]

    upload_required = bool(data.get("upload_required")) if "upload_required" in data else not matched
    next_step = str(data.get("next_step") or "").strip()
    if not matched and not next_step:
        next_step = UPLOAD_GUIDANCE
    if matched and match_kind == "fuzzy" and not next_step:
        next_step = (
            f'Fuzzy match to "{project_name}". Continue if this is the right project, '
            "or choose a different name from the accessible list."
        )
    if matched and match_kind == "exact" and not next_step:
        next_step = f'Confirmed project "{project_name}". Continue to scope the extraction.'

    if not matched and not rationale:
        names = ", ".join(row["name"] for row in accessible[:5]) or "none found"
        rationale = (
            "Could not find that project in accessible Datagrid documents. "
            f"Projects currently available: {names}."
        )

    steps = data.get("reasoning_steps") if isinstance(data.get("reasoning_steps"), list) else []
    reasoning = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        label = str(step.get("label") or "").strip()
        if not label:
            continue
        reasoning.append(
            {
                "id": str(step.get("id") or f"step-{len(reasoning)+1}"),
                "label": label,
                "status": str(step.get("status") or "done"),
                "detail": str(step.get("detail") or "").strip(),
            }
        )

    alternatives = []
    for row in accessible:
        alternatives.append(
            {
                "id": row.get("knowledge_id") or row["name"],
                "name": row["name"],
                "notes": row.get("notes") or "",
                "knowledge_id": row.get("knowledge_id"),
                "knowledge_name": row.get("knowledge_name") or row["name"],
            }
        )

    return {
        "matched": matched,
        "match_kind": match_kind,
        "project_name": project_name,
        "knowledge_id": knowledge_id,
        "knowledge_name": knowledge_name,
        "confidence": confidence,
        "rationale": rationale,
        "evidence": evidence_clean,
        "accessible_projects": accessible,
        "alternatives": alternatives[:8],
        "upload_required": upload_required,
        "next_step": next_step,
        "reasoning": reasoning,
        "candidates": ranked[:5],
    }


def no_match_payload(
    project: str,
    *,
    catalog: list[dict[str, Any]] | None = None,
    detail: str = "",
) -> dict[str, Any]:
    catalog = catalog or []
    accessible = [
        {
            "name": item["name"],
            "notes": f"Knowledge source ({item.get('status') or 'unknown'})",
            "knowledge_id": item["id"],
            "knowledge_name": item["name"],
        }
        for item in catalog[:12]
    ]
    names = ", ".join(row["name"] for row in accessible[:5]) or "none found in catalog"
    return {
        "matched": False,
        "match_kind": "none",
        "project_name": None,
        "knowledge_id": None,
        "knowledge_name": None,
        "confidence": "low",
        "rationale": (
            detail
            or (
                f'Could not confirm "{project}" in Datagrid data. '
                f"Accessible projects/knowledge: {names}."
            )
        ),
        "evidence": [],
        "accessible_projects": accessible,
        "alternatives": [
            {
                "id": row["knowledge_id"] or row["name"],
                "name": row["name"],
                "notes": row.get("notes") or "",
                "knowledge_id": row.get("knowledge_id"),
                "knowledge_name": row.get("knowledge_name"),
            }
            for row in accessible
        ],
        "upload_required": True,
        "next_step": UPLOAD_GUIDANCE,
        "reasoning": [
            {
                "id": "search",
                "label": "Deep search could not confirm the project",
                "status": "partial",
                "detail": detail or "No usable match returned from document search",
            }
        ],
        "candidates": [],
    }
