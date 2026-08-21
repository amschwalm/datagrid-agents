#!/usr/bin/env python3
"""Stage 3: run many Datagrid converse jobs concurrently with retry-on-stall.

Job schema (jobs.json is a list, or {"jobs": [...], "teamspace": "..."}):
  tag, agent | agent_id, prompt, teamspace?, conversation_id?,
  max_retries?, knowledge_ids?, chat_mode?
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from datagrid_client import DatagridClient, DatagridError  # noqa: E402

STALL_MARKERS = (
    "please retry",
    "try again",
    "couldn't retrieve",
    "could not retrieve",
    "wasn't able to retrieve",
    "was not able to retrieve",
    "unable to retrieve",
    "data gap",
    "i don't have access",
    "i do not have access",
    "not provided",
    "no data available",
    "couldn't find",
    "could not find the data",
)
NUDGE = (
    "You stopped after retrieving schemas. Now EXECUTE the queries and return "
    "the actual values, each with its source. Don't return a framework or schema."
)


def looks_stalled(text: str, tool_call_count: int) -> bool:
    lowered = (text or "").lower()
    if not lowered.strip():
        return True
    marked = any(marker in lowered for marker in STALL_MARKERS)
    if marked and tool_call_count <= 2:
        return True
    if marked and len(lowered) < 1200:
        return True
    return False


def _slug(value: str) -> str:
    keep = []
    for ch in (value or "").lower():
        keep.append(ch if ch.isalnum() else "-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "job"


def load_jobs(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    default_ts = None
    if isinstance(raw, dict):
        default_ts = raw.get("teamspace") or raw.get("teamspace_id")
        jobs = raw.get("jobs") or raw.get("items") or []
    elif isinstance(raw, list):
        jobs = raw
    else:
        raise SystemExit(f"jobs file must be a list or object with 'jobs': {path}")
    return list(jobs), default_ts


def _write_job(out_dir: Path, result: dict[str, Any]) -> None:
    tag = result["tag"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{tag}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    lines = [
        f"# {tag}",
        "",
        f"- agent: {result.get('agent_name') or result.get('agent_id')}",
        f"- stalled: {'yes' if result.get('stalled') else 'no'}",
        f"- retries: {result.get('retries', 0)}",
        f"- tool_calls: {result.get('tool_calls', 0)}",
        f"- credits: {result.get('credits')}",
        f"- conversation_id: {result.get('conversation_id')}",
        f"- chars: {len(result.get('text') or '')}",
        "",
        result.get("text") or "_empty_",
        "",
    ]
    if result.get("error"):
        lines.insert(2, f"- error: {result['error']}")
    (out_dir / f"{tag}.md").write_text("\n".join(lines), encoding="utf-8")


def run_one(
    client: DatagridClient,
    job: dict[str, Any],
    *,
    default_teamspace: str | None,
    default_retries: int,
) -> dict[str, Any]:
    tag = job.get("tag") or _slug(job.get("agent") or job.get("agent_id") or "job")
    prompt = (job.get("prompt") or "").strip()
    started = time.time()
    result: dict[str, Any] = {
        "tag": tag,
        "prompt": prompt,
        "ok": False,
        "stalled": False,
        "retries": 0,
        "tool_calls": 0,
        "credits": None,
        "conversation_id": job.get("conversation_id"),
        "text": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if not prompt:
        result["error"] = "empty prompt"
        result["elapsed_s"] = round(time.time() - started, 2)
        return result

    teamspace = job.get("teamspace") or default_teamspace
    try:
        if job.get("agent_id"):
            agent_id = job["agent_id"]
            agent_name = job.get("agent") or job.get("agent_name")
        else:
            agent = client.find_agent(str(job.get("agent") or ""), teamspace=teamspace)
            agent_id = agent["id"]
            agent_name = agent.get("name")
    except DatagridError as exc:
        result["error"] = str(exc)
        result["elapsed_s"] = round(time.time() - started, 2)
        return result

    result["agent_id"] = agent_id
    result["agent_name"] = agent_name
    knowledge_ids = job.get("knowledge_ids") or []
    chat_mode = job.get("chat_mode") or "full_agent"
    max_retries = int(job.get("max_retries") if job.get("max_retries") is not None else default_retries)
    conversation_id = job.get("conversation_id")
    current_prompt = prompt
    last_text = ""
    last_tools = 0
    last_credits = None
    last_response: dict[str, Any] | None = None
    stalled = False

    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            response = client.converse(
                current_prompt,
                agent_id=agent_id,
                conversation_id=conversation_id,
                chat_mode=chat_mode,
                teamspace=teamspace,
                knowledge_ids=knowledge_ids,
            )
        except DatagridError as exc:
            result["error"] = str(exc)
            result["retries"] = attempt
            result["elapsed_s"] = round(time.time() - started, 2)
            return result

        last_response = response if isinstance(response, dict) else None
        last_text = DatagridClient.converse_text(response)
        last_tools = len(DatagridClient.converse_tool_calls(response))
        last_credits = DatagridClient.converse_credits(response)
        if isinstance(response, dict):
            conversation_id = response.get("conversation_id") or conversation_id

        stalled = looks_stalled(last_text, last_tools)
        if not stalled:
            break
        if attempt + 1 >= attempts:
            break
        current_prompt = NUDGE
        result["retries"] = attempt + 1

    result.update(
        {
            "ok": bool(last_text) and not stalled,
            "stalled": stalled,
            "text": last_text,
            "tool_calls": last_tools,
            "credits": last_credits,
            "conversation_id": conversation_id,
            "elapsed_s": round(time.time() - started, 2),
            "response_keys": sorted(last_response.keys()) if last_response else [],
        }
    )
    return result


def write_summary(out_dir: Path, results: list[dict[str, Any]]) -> None:
    lines = [
        "# Orchestrator summary",
        "",
        f"- jobs: {len(results)}",
        f"- ok: {sum(1 for r in results if r.get('ok'))}",
        f"- stalled: {sum(1 for r in results if r.get('stalled'))}",
        f"- errors: {sum(1 for r in results if r.get('error'))}",
        "",
        "| tag | agent | stalled | retries | tools | credits | chars |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            "| {tag} | {agent} | {stalled} | {retries} | {tools} | {credits} | {chars} |".format(
                tag=r.get("tag"),
                agent=r.get("agent_name") or r.get("agent_id") or "",
                stalled="yes" if r.get("stalled") else "no",
                retries=r.get("retries", 0),
                tools=r.get("tool_calls", 0),
                credits=r.get("credits") if r.get("credits") is not None else "",
                chars=len(r.get("text") or ""),
            )
        )
    lines.append("")
    (out_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def run_jobs(
    jobs: list[dict[str, Any]],
    *,
    out_dir: Path,
    concurrency: int,
    default_teamspace: str | None,
    default_retries: int,
    client: DatagridClient | None = None,
) -> list[dict[str, Any]]:
    client = client or DatagridClient(teamspace=default_teamspace)
    out_dir.mkdir(parents=True, exist_ok=True)
    used_tags: dict[str, int] = {}
    prepared = []
    for job in jobs:
        job = dict(job)
        tag = _slug(str(job.get("tag") or job.get("agent") or job.get("agent_id") or "job"))
        n = used_tags.get(tag, 0)
        used_tags[tag] = n + 1
        if n:
            tag = f"{tag}-{n + 1}"
        job["tag"] = tag
        prepared.append(job)

    results: list[dict[str, Any]] = []
    workers = max(1, int(concurrency))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_one,
                client,
                job,
                default_teamspace=default_teamspace,
                default_retries=default_retries,
            ): job
            for job in prepared
        }
        for fut in as_completed(futures):
            result = fut.result()
            _write_job(out_dir, result)
            results.append(result)
            status = "ERR" if result.get("error") else ("STALL" if result.get("stalled") else "OK")
            print(f"[{status}] {result['tag']} tools={result.get('tool_calls')} chars={len(result.get('text') or '')}")
    results.sort(key=lambda r: r.get("tag") or "")
    write_summary(out_dir, results)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Concurrent Datagrid converse runner.")
    parser.add_argument("--jobs", help="jobs.json (list or {jobs:[...]})")
    parser.add_argument("--agents", help="Comma-separated agent names/ids (with --prompt)")
    parser.add_argument("--prompt", "-p", help="Shared prompt when using --agents")
    parser.add_argument("--teamspace", "-t", help="Default teamspace name or id")
    parser.add_argument("--out", default="results", help="Output directory")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv)

    default_ts = args.teamspace
    if args.jobs:
        jobs, file_ts = load_jobs(Path(args.jobs))
        default_ts = default_ts or file_ts
    elif args.agents and args.prompt:
        jobs = []
        for name in [p.strip() for p in args.agents.split(",") if p.strip()]:
            job: dict[str, Any] = {"tag": _slug(name), "prompt": args.prompt, "teamspace": default_ts}
            if re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                name,
            ):
                job["agent_id"] = name
            else:
                job["agent"] = name
            jobs.append(job)
    else:
        parser.error("Provide --jobs FILE or both --agents and --prompt")
        return 2

    # Skip empty template prompts unless this is an --agents run.
    if args.jobs:
        nonempty = [j for j in jobs if str(j.get("prompt") or "").strip()]
        skipped = len(jobs) - len(nonempty)
        if skipped:
            print(f"Skipping {skipped} jobs with empty prompts", file=sys.stderr)
        jobs = nonempty
        if not jobs:
            print("No jobs with prompts. Fill jobs_template.json first.", file=sys.stderr)
            return 2

    results = run_jobs(
        jobs,
        out_dir=Path(args.out),
        concurrency=args.concurrency,
        default_teamspace=default_ts,
        default_retries=args.max_retries,
    )
    stalled = sum(1 for r in results if r.get("stalled") or r.get("error"))
    print(f"Wrote {args.out}/SUMMARY.md ({len(results)} jobs, {stalled} stalled/errors)")
    return 0 if stalled == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatagridError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
