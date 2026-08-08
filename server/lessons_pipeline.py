"""Multi-pass lessons extraction via Datagrid orchestrator fan-out."""

from __future__ import annotations

import os
from typing import Any, Callable

from datagrid_agents.orchestrator.parallel import AgentCall, AgentResult, run_parallel
from datagrid_agents.orchestrator.registry import load_role
from datagrid_agents.orchestrator.workflows.lessons_multipass import (
    ANALYSIS_LENSES,
    ANALYSIS_PASSES,
    ROLE_KEY,
    build_analysis_prompt,
    build_pass_calls,
)
from server.jsonutil import extract_json

TARGET_FINDINGS = 50

# Visual graph nodes the UI animates while passes run.
GRAPH_NODES = [
    "RFIs",
    "Meetings",
    "Change Events",
    "Submittals",
    "Specs",
    "Daily Reports",
    "Buyout",
    "Schedule",
    "Punchlist",
    "As-Builts",
]

# Re-export for tests / callers that imported these from this module.
__all__ = [
    "ANALYSIS_LENSES",
    "ANALYSIS_PASSES",
    "TARGET_FINDINGS",
    "GRAPH_NODES",
    "build_analysis_prompt",
    "build_aggregate_prompt",
    "ensure_fifty",
    "local_aggregate",
    "parse_aggregate_result",
    "parse_pass_result",
    "run_multipass_extraction",
]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def lessons_max_workers(override: int | None = None) -> int:
    """Higher default concurrency than general orchestrator fan-out (20 passes)."""
    if override is not None:
        return max(1, override)
    return max(1, _env_int("DATAGRID_ORCH_LESSONS_MAX_WORKERS", 20))


def lessons_timeout_seconds(override: float | None = None) -> float:
    if override is not None:
        return override
    # Prefer lessons-specific timeout, then general orch timeout, then 180s.
    if os.environ.get("DATAGRID_ORCH_LESSONS_TIMEOUT_SECONDS", "").strip():
        return _env_float("DATAGRID_ORCH_LESSONS_TIMEOUT_SECONDS", 180.0)
    if os.environ.get("DATAGRID_ORCH_TIMEOUT_SECONDS", "").strip():
        return _env_float("DATAGRID_ORCH_TIMEOUT_SECONDS", 180.0)
    return 180.0


def build_aggregate_prompt(prompt: str, interview: str, pass_payloads: list[dict[str, Any]]) -> str:
    return f"""
You are the aggregation analyst for a multi-pass construction lessons-learned extraction.

## Opening statement
{prompt}

## Follow-up interview
{interview}

## Pass results ({len(pass_payloads)} analysis calls)
{pass_payloads}

## Task
1. Cross-reference findings across passes. Merge duplicates; keep the strongest wording.
2. Resolve conflicts by preferring findings with clearer evidence and higher recurrence.
3. Produce EXACTLY {TARGET_FINDINGS} ranked findings (no fewer, no more).
4. Write a short executive summary and 5 institutional actions.

Return ONLY valid JSON:
{{
  "summary": "5-8 sentence executive summary",
  "actions": ["action 1", "action 2", "action 3", "action 4", "action 5"],
  "findings": [
    {{
      "rank": 1,
      "finding": "title",
      "category": "category",
      "evidence": "evidence",
      "recommendation": "recommendation",
      "priority": "high|med|low",
      "sources": ["cost", "schedule"]
    }}
  ]
}}
The findings array MUST contain exactly {TARGET_FINDINGS} objects ranked 1..{TARGET_FINDINGS}.
""".strip()


def normalize_finding(raw: dict[str, Any], *, default_sources: list[str] | None = None) -> dict[str, Any]:
    priority = str(raw.get("priority") or "med").strip().lower()
    if priority not in {"high", "med", "low"}:
        priority = "med"
    sources = raw.get("sources") or raw.get("artifacts") or default_sources or []
    if isinstance(sources, str):
        sources = [sources]
    return {
        "finding": str(raw.get("finding") or raw.get("title") or "Untitled finding").strip(),
        "category": str(raw.get("category") or "General").strip(),
        "evidence": str(raw.get("evidence") or "").strip(),
        "recommendation": str(raw.get("recommendation") or "").strip(),
        "priority": priority,
        "sources": [str(s).strip() for s in sources if str(s).strip()],
    }


def parse_pass_result(text: str, lens: dict[str, str]) -> dict[str, Any]:
    data = extract_json(text)
    if not isinstance(data, dict):
        return {
            "lens": lens["id"],
            "summary": (text or "").strip()[:400],
            "findings": [],
            "raw_text": text,
            "parse_ok": False,
        }
    findings_raw = data.get("findings") or []
    findings = []
    if isinstance(findings_raw, list):
        for item in findings_raw:
            if isinstance(item, dict):
                findings.append(normalize_finding(item, default_sources=[lens["id"]]))
    return {
        "lens": lens["id"],
        "title": lens["title"],
        "summary": str(data.get("summary") or "").strip(),
        "findings": findings,
        "parse_ok": True,
    }


def local_aggregate(pass_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic fallback if the aggregate agent call fails or under-delivers."""
    bucket: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in pass_results:
        lens = str(result.get("lens") or "unknown")
        for finding in result.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            key = finding.get("finding", "").strip().lower()
            if not key or key in seen:
                # merge sources into existing if duplicate
                if key in seen:
                    for existing in bucket:
                        if existing["finding"].strip().lower() == key:
                            sources = set(existing.get("sources") or [])
                            sources.update(finding.get("sources") or [lens])
                            existing["sources"] = sorted(sources)
                            break
                continue
            seen.add(key)
            item = normalize_finding(finding, default_sources=[lens])
            bucket.append(item)

    priority_rank = {"high": 0, "med": 1, "low": 2}
    bucket.sort(key=lambda f: (priority_rank.get(f["priority"], 1), -len(f.get("sources") or [])))

    # Pad to 50 with synthesized placeholders derived from lens summaries if needed.
    idx = 0
    while len(bucket) < TARGET_FINDINGS:
        result = pass_results[idx % max(len(pass_results), 1)] if pass_results else {}
        lens = result.get("title") or result.get("lens") or "General"
        summary = result.get("summary") or "Additional institutional lesson inferred from pass coverage."
        bucket.append(
            {
                "finding": f"Follow-up control for {lens}",
                "category": str(lens),
                "evidence": str(summary)[:280],
                "recommendation": "Codify a checklist item and owner for this risk on the next project.",
                "priority": "med",
                "sources": [str(result.get("lens") or "aggregate")],
            }
        )
        idx += 1

    findings = []
    for i, item in enumerate(bucket[:TARGET_FINDINGS], start=1):
        findings.append({"rank": i, **item})

    summaries = [r.get("summary") for r in pass_results if r.get("summary")]
    summary = " ".join(str(s) for s in summaries[:4]).strip()
    if not summary:
        summary = "Multi-pass extraction completed. Findings below are cross-referenced from specialized analysis lenses."

    return {
        "summary": summary,
        "actions": [
            "Stand up a lessons register owner within 48 hours of closeout.",
            "Translate top high-priority findings into playbook checklist items.",
            "Brief the next project team on the top ten findings before buyout.",
            "Tie recurring RFI / change themes to design-review gates.",
            "Audit whether prior lessons were actually applied on the next job.",
        ],
        "findings": findings,
        "aggregated_locally": True,
    }


def ensure_fifty(aggregate: dict[str, Any], pass_results: list[dict[str, Any]]) -> dict[str, Any]:
    findings_raw = aggregate.get("findings") if isinstance(aggregate, dict) else None
    if not isinstance(findings_raw, list) or len(findings_raw) < TARGET_FINDINGS:
        fallback = local_aggregate(pass_results)
        # Prefer model summary/actions when present.
        if isinstance(aggregate, dict):
            if aggregate.get("summary"):
                fallback["summary"] = str(aggregate["summary"]).strip()
            if isinstance(aggregate.get("actions"), list) and aggregate["actions"]:
                fallback["actions"] = [str(a).strip() for a in aggregate["actions"] if str(a).strip()][:8]
            # Use any model findings first, then pad from local aggregate.
            model_findings = []
            for item in findings_raw or []:
                if isinstance(item, dict):
                    model_findings.append(normalize_finding(item))
            merged = model_findings + [
                f for f in fallback["findings"] if f["finding"].lower() not in {m["finding"].lower() for m in model_findings}
            ]
            ranked = []
            for i, item in enumerate(merged[:TARGET_FINDINGS], start=1):
                ranked.append({"rank": i, **{k: v for k, v in item.items() if k != "rank"}})
            # if still short, local_aggregate already pads
            while len(ranked) < TARGET_FINDINGS:
                pad = fallback["findings"][len(ranked) % len(fallback["findings"])]
                ranked.append({"rank": len(ranked) + 1, **{k: v for k, v in pad.items() if k != "rank"}})
            fallback["findings"] = ranked[:TARGET_FINDINGS]
            fallback["aggregated_locally"] = True
        return fallback

    findings = []
    for i, item in enumerate(findings_raw[:TARGET_FINDINGS], start=1):
        if not isinstance(item, dict):
            continue
        normalized = normalize_finding(item)
        findings.append({"rank": i, **normalized})

    while len(findings) < TARGET_FINDINGS:
        pad = local_aggregate(pass_results)["findings"][len(findings)]
        findings.append({"rank": len(findings) + 1, **{k: v for k, v in pad.items() if k != "rank"}})

    actions = aggregate.get("actions") if isinstance(aggregate.get("actions"), list) else []
    return {
        "summary": str(aggregate.get("summary") or "").strip(),
        "actions": [str(a).strip() for a in actions if str(a).strip()][:8],
        "findings": findings[:TARGET_FINDINGS],
        "aggregated_locally": False,
    }


def parse_aggregate_result(text: str, pass_results: list[dict[str, Any]]) -> dict[str, Any]:
    data = extract_json(text)
    if not isinstance(data, dict):
        result = local_aggregate(pass_results)
        result["raw_text"] = text
        return result
    result = ensure_fifty(data, pass_results)
    result["raw_text"] = text
    return result


EventCallback = Callable[[str, dict[str, Any]], None]
ConverseFn = Callable[[AgentCall], Any]


def run_multipass_extraction(
    *,
    prompt: str,
    interview: str,
    converse: ConverseFn | None = None,
    on_event: EventCallback | None = None,
    max_workers: int | None = None,
    timeout_seconds: float | None = None,
    cache: bool = False,
    role_key: str = ROLE_KEY,
) -> dict[str, Any]:
    """Run 20 analysis calls through the orchestrator, then one aggregate call."""

    def emit(event: str, data: dict[str, Any]) -> None:
        if on_event:
            on_event(event, data)

    role = load_role(role_key)
    workers = lessons_max_workers(max_workers)
    timeout = lessons_timeout_seconds(timeout_seconds)
    lenses = ANALYSIS_LENSES[:ANALYSIS_PASSES]
    calls = build_pass_calls(prompt, interview, role_key=role_key, lenses=lenses)

    emit(
        "step",
        {
            "id": "prepare",
            "label": "Preparing 20 specialized analysis passes",
            "status": "done",
            "detail": f"{len(calls)} lenses via orchestrator fan-out (max {workers} workers)",
        },
    )

    pass_results: list[dict[str, Any] | None] = [None] * len(calls)
    completed = 0

    def on_result(index: int, _call: AgentCall, result: AgentResult) -> None:
        nonlocal completed
        lens = lenses[index]
        text = result.text if result.ok else f"(pass error: {result.error})"
        parsed = parse_pass_result(text, lens)
        parsed["agent"] = {
            "agent_id": result.agent_id or role.id,
            "agent_name": role.name,
            "conversation_id": result.conversation_id,
            "cached": result.cached,
            "error": result.error,
        }
        pass_results[index] = parsed
        completed += 1
        link_nodes = [n.strip() for n in lens.get("links", "").split(",") if n.strip()]
        emit(
            "pass",
            {
                "index": index + 1,
                "total": len(calls),
                "completed": completed,
                "lens": lens["id"],
                "title": lens["title"],
                "status": "done" if parsed.get("parse_ok") else "partial",
                "finding_count": len(parsed.get("findings") or []),
                "summary": parsed.get("summary") or "",
                "links": link_nodes,
                "orchestrator": True,
                "cached": result.cached,
            },
        )
        if len(link_nodes) >= 2:
            emit("link", {"from": link_nodes[0], "to": link_nodes[1], "via": lens["title"]})
        if len(link_nodes) >= 3:
            emit("link", {"from": link_nodes[1], "to": link_nodes[2], "via": lens["title"]})

    emit(
        "step",
        {
            "id": "passes",
            "label": f"Orchestrator running {len(calls)} parallel analysis API calls",
            "status": "running",
            "detail": f"Concurrency {workers} · timeout {timeout:.0f}s",
        },
    )

    run_parallel(
        calls,
        max_workers=workers,
        timeout_seconds=timeout,
        # 20 passes (+ headroom); do not inherit the general orch max_calls=12 default.
        max_calls=max(len(calls) + 2, 24),
        cache=cache,
        converse=converse,
        on_result=on_result,
    )

    emit(
        "step",
        {
            "id": "passes",
            "label": f"Completed {len(calls)} analysis API calls",
            "status": "done",
            "detail": f"{sum(len((r or {}).get('findings') or []) for r in pass_results)} raw findings collected",
        },
    )

    compact_passes = []
    for result in pass_results:
        if not result:
            continue
        compact_passes.append(
            {
                "lens": result.get("lens"),
                "title": result.get("title"),
                "summary": result.get("summary"),
                "findings": result.get("findings") or [],
            }
        )

    emit(
        "step",
        {
            "id": "aggregate",
            "label": "Cross-referencing passes into aggregate top 50",
            "status": "running",
            "detail": "Merging duplicates and ranking by evidence strength",
        },
    )

    aggregate_call = AgentCall(
        role=f"{role_key}:aggregate",
        agent_id=role.id,
        prompt=build_aggregate_prompt(prompt, interview, compact_passes),
        chat_mode=role.chat_mode or "full_agent",
    )
    aggregate_results = run_parallel(
        [aggregate_call],
        max_workers=1,
        timeout_seconds=timeout,
        max_calls=1,
        cache=cache,
        converse=converse,
    )
    aggregate_response = aggregate_results[0]
    aggregate_text = (
        aggregate_response.text
        if aggregate_response.ok
        else f"(aggregate error: {aggregate_response.error})"
    )
    aggregate = parse_aggregate_result(aggregate_text, [r for r in pass_results if r])

    emit(
        "step",
        {
            "id": "aggregate",
            "label": "Aggregate ranking complete",
            "status": "done",
            "detail": f"{len(aggregate.get('findings') or [])} findings finalized",
        },
    )

    emit(
        "step",
        {
            "id": "table",
            "label": "Building top-50 findings table",
            "status": "done",
            "detail": "Structured table ready for review and follow-up questions",
        },
    )

    return {
        "summary": aggregate.get("summary") or "",
        "actions": aggregate.get("actions") or [],
        "findings": aggregate.get("findings") or [],
        "pass_count": len(calls),
        "passes_completed": completed,
        "aggregated_locally": bool(aggregate.get("aggregated_locally")),
        "orchestrator": {
            "workflow": "lessons_multipass",
            "max_workers": workers,
            "timeout_seconds": timeout,
            "cache": bool(cache),
        },
        "graph_nodes": GRAPH_NODES,
        "result": {
            "role": role_key,
            "agent_id": aggregate_response.agent_id or role.id,
            "agent_name": role.name,
            "text": aggregate.get("summary") or "",
            "conversation_id": aggregate_response.conversation_id,
        },
        "passes": compact_passes,
    }
