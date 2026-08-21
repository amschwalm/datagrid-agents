#!/usr/bin/env python3
"""Stage 1: profile a teamspace (knowledge + tables + agents + AI-search sweep)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from datagrid_client import DatagridClient, DatagridError  # noqa: E402

DEFAULT_QUERIES = [
    "What projects, documents, and data sources exist here?",
    "What tables, files, and knowledge bases are available, and what do they contain?",
    "What are the main topics, risks, outstanding issues, and named entities?",
    "What key figures, dates, lead times, and commercial facts appear in the data?",
]


def _slug(value: str) -> str:
    keep = []
    for ch in (value or "").lower():
        keep.append(ch if ch.isalnum() else "-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "agent"


def _search_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "").strip()
    for key in ("answer", "output_text", "text", "content"):
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list):
            parts = []
            for item in val:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts).strip()
    return json.dumps(result, default=str)[:2000]


def _knowledge_status(item: dict[str, Any]) -> str:
    return (
        item.get("status")
        or item.get("indexing_status")
        or item.get("state")
        or ""
    )


def explore(
    teamspace: str,
    out_dir: Path,
    queries: list[str],
    client: DatagridClient | None = None,
) -> dict[str, Any]:
    client = client or DatagridClient(teamspace=teamspace)
    ts_id = client.resolve_teamspace(teamspace)
    ts_name = teamspace
    try:
        detail = client.get_teamspace(ts_id) if ts_id else {}
        ts_name = detail.get("name") or teamspace
    except DatagridError:
        detail = {}

    identity = client.whoami()
    agents = client.list_agents(teamspace=ts_id)
    # /knowledge is always the key's home teamspace, regardless of header.
    knowledge = client.list_knowledge(teamspace=ts_id)
    detailed_knowledge = []
    for item in knowledge:
        kid = item.get("id")
        rec = dict(item)
        if kid:
            try:
                rec = client.get_knowledge(kid, teamspace=ts_id)
            except DatagridError as exc:
                rec = dict(item)
                rec["retrieve_error"] = str(exc)
        detailed_knowledge.append(rec)

    knowledge_ids = {k.get("id") for k in detailed_knowledge if k.get("id")}
    tables_all = client.list_tables(teamspace=ts_id)
    tables = [
        t for t in tables_all if t.get("knowledge_id") in knowledge_ids
    ] if knowledge_ids else []

    searches = []
    for query in queries:
        entry: dict[str, Any] = {"query": query}
        try:
            result = client.ai_search(query, teamspace=ts_id)
            entry["ok"] = True
            entry["answer"] = _search_text(result)
            entry["raw"] = result
        except DatagridError as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        searches.append(entry)

    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "teamspace": {
            "name": ts_name,
            "id": ts_id,
            "access": detail.get("access"),
            "cloud_provider": detail.get("cloud_provider"),
        },
        "identity": {
            "user_id": identity.get("user_id"),
            "current_teamspace_id": identity.get("current_teamspace_id"),
        },
        "knowledge": detailed_knowledge,
        "knowledge_note": (
            "/knowledge lists the API key's home teamspace "
            f"({identity.get('current_teamspace_id')}), not an arbitrary "
            "Datagrid-Teamspace header target."
        ),
        "tables": tables,
        "tables_unscoped_count": len(tables_all),
        "agents": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "description": (a.get("description") or "").strip(),
                "agent_model": a.get("agent_model"),
                "llm_model": a.get("llm_model"),
            }
            for a in agents
        ],
        "ai_search": [
            {k: v for k, v in s.items() if k != "raw"} for s in searches
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "profile.json").write_text(
        json.dumps(profile, indent=2, default=str), encoding="utf-8"
    )

    jobs = {
        "teamspace": ts_name,
        "teamspace_id": ts_id,
        "jobs": [
            {
                "tag": _slug(a.get("name") or a.get("id") or "agent"),
                "agent": a.get("name"),
                "agent_id": a.get("id"),
                "prompt": "",
                "teamspace": ts_name,
                "knowledge_ids": [],
            }
            for a in agents
        ],
    }
    (out_dir / "jobs_template.json").write_text(
        json.dumps(jobs, indent=2), encoding="utf-8"
    )

    lines = [
        f"# Teamspace profile: {ts_name}",
        "",
        f"- id: `{ts_id}`",
        f"- generated: {profile['generated_at']}",
        f"- key home teamspace: `{identity.get('current_teamspace_id')}`",
        f"- agents: {len(agents)}",
        f"- knowledge items: {len(detailed_knowledge)}",
        f"- tables scoped to those knowledge ids: {len(tables)} "
        f"(unscoped /tables rows: {len(tables_all)})",
        "",
        "## Knowledge",
        "",
        profile["knowledge_note"],
        "",
    ]
    if not detailed_knowledge:
        lines.append("_No knowledge items visible to this API key._")
    for item in detailed_knowledge:
        name = item.get("name") or item.get("id")
        status = _knowledge_status(item) or "unknown"
        lines.append(
            f"- **{name}** `{item.get('id')}` status=`{status}` "
            f"type=`{item.get('object') or item.get('type') or ''}`"
        )
        if item.get("retrieve_error"):
            lines.append(f"  - retrieve error: {item['retrieve_error']}")
    lines += ["", "## Tables (scoped)", ""]
    if not tables:
        lines.append("_No tables whose knowledge_id is in list_knowledge()._")
    for table in tables:
        lines.append(
            f"- **{table.get('name') or table.get('id')}** `{table.get('id')}` "
            f"knowledge=`{table.get('knowledge_id')}`"
        )
    lines += ["", "## Agents", ""]
    for agent in profile["agents"]:
        desc = agent["description"].replace("\n", " ")
        if len(desc) > 160:
            desc = desc[:157] + "..."
        lines.append(f"- **{agent['name']}** `{agent['id']}`")
        if desc:
            lines.append(f"  - {desc}")
    lines += ["", "## AI search sweep", ""]
    for sweep in searches:
        lines.append(f"### {sweep['query']}")
        lines.append("")
        if sweep.get("ok"):
            lines.append(sweep.get("answer") or "_empty_")
        else:
            lines.append(f"_error:_ {sweep.get('error')}")
        lines.append("")
    lines += [
        "## Next: write targeted prompts",
        "",
        "Edit `jobs_template.json`. Fill each `prompt` with concrete questions that "
        "name the documents, tables, and figures above. Attach knowledge ids via "
        "`knowledge_ids` when an agent corpus may not include a file.",
        "",
        "Then dispatch:",
        "",
        "```bash",
        "python scripts/orchestrate.py --jobs profile/jobs_template.json --out results --concurrency 6",
        "```",
        "",
    ]
    (out_dir / "profile.md").write_text("\n".join(lines), encoding="utf-8")
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a Datagrid teamspace.")
    parser.add_argument("--teamspace", "-t", required=True, help="Teamspace name or id")
    parser.add_argument("--out", default="profile", help="Output directory (default: profile)")
    parser.add_argument(
        "--queries",
        help="Optional file of extra AI-search probes (one per line)",
    )
    args = parser.parse_args(argv)
    queries = list(DEFAULT_QUERIES)
    if args.queries:
        extra = Path(args.queries).read_text(encoding="utf-8").splitlines()
        queries.extend(q.strip() for q in extra if q.strip() and not q.strip().startswith("#"))
    profile = explore(args.teamspace, Path(args.out), queries)
    print(
        f"Wrote {args.out}/profile.md, profile.json, jobs_template.json "
        f"({len(profile['agents'])} agents, {len(profile['knowledge'])} knowledge)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatagridError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
