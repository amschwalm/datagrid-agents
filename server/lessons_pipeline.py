"""Multi-pass lessons extraction: 20 analysis lenses + aggregate top-50."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from server.jsonutil import extract_json

ANALYSIS_PASSES = 20
TARGET_FINDINGS = 50
MAX_WORKERS = 5

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

# Each pass analyzes through a different construction lens.
ANALYSIS_LENSES: list[dict[str, str]] = [
    {
        "id": "cost",
        "title": "Cost & contingency",
        "focus": "cost growth, contingency burn, extras, buyout gaps, and money left on the table",
        "links": "Buyout,Change Events,RFIs",
    },
    {
        "id": "schedule",
        "title": "Schedule & sequencing",
        "focus": "logic ties, float burn, shutdown windows, trade stacking, and recovery options",
        "links": "Schedule,Meetings,Change Events",
    },
    {
        "id": "procurement",
        "title": "Procurement & buyout",
        "focus": "package strategy, vendor commitment, long-lead risk, and scope gaps at buyout",
        "links": "Buyout,Submittals,Schedule",
    },
    {
        "id": "design_rfi",
        "title": "Design coordination & RFIs",
        "focus": "drawing conflicts, RFI latency, incomplete design, and late clarifications",
        "links": "RFIs,Specs,As-Builts",
    },
    {
        "id": "change",
        "title": "Change management",
        "focus": "change events, entitlement, pricing discipline, and owner direction timing",
        "links": "Change Events,Meetings,RFIs",
    },
    {
        "id": "safety",
        "title": "Safety & field risk",
        "focus": "unsafe conditions, near misses, logistics conflicts, and field readiness",
        "links": "Daily Reports,Meetings,Schedule",
    },
    {
        "id": "quality",
        "title": "Quality & rework",
        "focus": "rework drivers, inspection failures, installation standards, and punch trends",
        "links": "Punchlist,Submittals,Daily Reports",
    },
    {
        "id": "owner",
        "title": "Owner decisions & approvals",
        "focus": "decision latency, ambiguous direction, approval bottlenecks, and scope creep",
        "links": "Meetings,Change Events,RFIs",
    },
    {
        "id": "trades",
        "title": "Trade coordination",
        "focus": "handoffs between trades, access conflicts, and multi-trade workface issues",
        "links": "Meetings,Schedule,Daily Reports",
    },
    {
        "id": "utilities",
        "title": "Utilities & site logistics",
        "focus": "utility coordination, shutdowns, laydown, access, and site constraint surprises",
        "links": "Schedule,Meetings,As-Builts",
    },
    {
        "id": "contract",
        "title": "Contracts & risk allocation",
        "focus": "contract gaps, notice failures, risk ownership, and commercial exposure",
        "links": "Change Events,RFIs,Meetings",
    },
    {
        "id": "comms",
        "title": "Communication & meetings",
        "focus": "who knew what when, meeting effectiveness, and information that never landed",
        "links": "Meetings,RFIs,Daily Reports",
    },
    {
        "id": "docs",
        "title": "Documentation & as-builts",
        "focus": "as-built accuracy, document control, and truth vs field conditions",
        "links": "As-Builts,Specs,RFIs",
    },
    {
        "id": "closeout",
        "title": "Closeout & turnover",
        "focus": "closeout package gaps, O&M readiness, commissioning, and turnover friction",
        "links": "Punchlist,Submittals,As-Builts",
    },
    {
        "id": "staffing",
        "title": "Labor & staffing",
        "focus": "crew availability, supervision bandwidth, and skill mismatches",
        "links": "Daily Reports,Schedule,Meetings",
    },
    {
        "id": "field",
        "title": "Field conditions",
        "focus": "unforeseen conditions, weather, access, and site reality vs plan",
        "links": "Daily Reports,Change Events,As-Builts",
    },
    {
        "id": "permitting",
        "title": "Permitting & AHJ",
        "focus": "inspection timing, code interpretations, and authority-having-jurisdiction friction",
        "links": "Submittals,Meetings,Schedule",
    },
    {
        "id": "bim",
        "title": "BIM & technology",
        "focus": "model coordination gaps, clash detection misses, and digital-to-field translation",
        "links": "RFIs,Specs,As-Builts",
    },
    {
        "id": "stakeholders",
        "title": "Stakeholder politics",
        "focus": "competing incentives, escalation paths, and decisions distorted by politics",
        "links": "Meetings,Change Events,RFIs",
    },
    {
        "id": "memory",
        "title": "Institutional memory",
        "focus": "repeatable process failures, what the org should bake into standards next time",
        "links": "Meetings,Specs,Punchlist",
    },
]


def build_analysis_prompt(lens: dict[str, str], prompt: str, interview: str) -> str:
    return f"""
You are running one specialized pass of a multi-pass lessons-learned extraction.

## Lens
{lens["title"]} — focus on {lens["focus"]}.

## Opening statement
{prompt}

## Follow-up interview
{interview}

## Task
Extract 4 to 8 concrete findings through THIS lens only.
Cross-link to project artifacts when plausible (RFIs, meetings, change events, submittals, specs, daily reports, buyout, schedule, punchlist, as-builts).

Return ONLY valid JSON:
{{
  "lens": "{lens["id"]}",
  "summary": "2-3 sentences",
  "findings": [
    {{
      "finding": "short title",
      "category": "category label",
      "evidence": "what in the account supports this",
      "recommendation": "what to do differently",
      "priority": "high|med|low",
      "artifacts": ["RFIs", "Meetings"]
    }}
  ]
}}
""".strip()


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


def run_multipass_extraction(
    *,
    prompt: str,
    interview: str,
    converse: Callable[[str], dict[str, Any]],
    on_event: EventCallback | None = None,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    """Run 20 analysis calls in parallel, then one aggregate call."""

    def emit(event: str, data: dict[str, Any]) -> None:
        if on_event:
            on_event(event, data)

    emit(
        "step",
        {
            "id": "prepare",
            "label": "Preparing 20 specialized analysis passes",
            "status": "done",
            "detail": f"{ANALYSIS_PASSES} lenses across cost, schedule, RFIs, changes, and more",
        },
    )

    pass_results: list[dict[str, Any] | None] = [None] * ANALYSIS_PASSES
    completed = 0

    def run_one(index: int, lens: dict[str, str]) -> tuple[int, dict[str, Any], dict[str, str]]:
        analysis_prompt = build_analysis_prompt(lens, prompt, interview)
        response = converse(analysis_prompt)
        parsed = parse_pass_result(response.get("text") or "", lens)
        parsed["agent"] = {
            "agent_id": response.get("agent_id"),
            "agent_name": response.get("agent_name"),
            "conversation_id": response.get("conversation_id"),
        }
        return index, parsed, lens

    emit(
        "step",
        {
            "id": "passes",
            "label": f"Running {ANALYSIS_PASSES} parallel analysis API calls",
            "status": "running",
            "detail": f"Concurrency {max_workers}",
        },
    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(run_one, index, lens): index
            for index, lens in enumerate(ANALYSIS_LENSES[:ANALYSIS_PASSES])
        }
        for future in as_completed(futures):
            index, parsed, lens = future.result()
            pass_results[index] = parsed
            completed += 1
            link_nodes = [n.strip() for n in lens.get("links", "").split(",") if n.strip()]
            emit(
                "pass",
                {
                    "index": index + 1,
                    "total": ANALYSIS_PASSES,
                    "completed": completed,
                    "lens": lens["id"],
                    "title": lens["title"],
                    "status": "done" if parsed.get("parse_ok") else "partial",
                    "finding_count": len(parsed.get("findings") or []),
                    "summary": parsed.get("summary") or "",
                    "links": link_nodes,
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
            "label": f"Completed {ANALYSIS_PASSES} analysis API calls",
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

    aggregate_response = converse(build_aggregate_prompt(prompt, interview, compact_passes))
    aggregate = parse_aggregate_result(aggregate_response.get("text") or "", [r for r in pass_results if r])

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
        "pass_count": ANALYSIS_PASSES,
        "passes_completed": completed,
        "aggregated_locally": bool(aggregate.get("aggregated_locally")),
        "graph_nodes": GRAPH_NODES,
        "result": {
            "role": "lessons_extractor",
            "agent_id": aggregate_response.get("agent_id"),
            "agent_name": aggregate_response.get("agent_name"),
            "text": aggregate.get("summary") or "",
            "conversation_id": aggregate_response.get("conversation_id"),
        },
        "passes": compact_passes,
    }
