#!/usr/bin/env python3
"""Thin wrapper so the Cursor skill can invoke orchestration workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    # Allow running from a fresh checkout before editable install by adding src/.
    repo_root = Path(__file__).resolve().parents[4]
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from datagrid_agents.orchestrator import list_workflows, run_workflow

    parser = argparse.ArgumentParser(
        description="Run a Datagrid orchestrator workflow for the Cursor skill.",
    )
    parser.add_argument(
        "workflow",
        nargs="?",
        help="Workflow name (omit with --list)",
    )
    parser.add_argument("--prompt", "-p", help="User goal / prompt text")
    parser.add_argument("--file", "-f", help="Read prompt from a file")
    parser.add_argument(
        "--context",
        "-c",
        action="append",
        default=[],
        help="Local file or directory to attach (repeatable)",
    )
    parser.add_argument(
        "--roles",
        help="Comma-separated roles for fanout (e.g. mentor,schedule,rfi)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="For fanout: call each role N times (default: 1)",
    )
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--runs-dir", default=".orchestrator/runs")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true", help="List workflows")
    args = parser.parse_args(argv)

    if args.list or not args.workflow:
        for name in list_workflows():
            print(name)
        return 0 if args.list or not args.workflow else 2

    prompt = args.prompt
    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    if not prompt:
        print("Provide --prompt or --file.", file=sys.stderr)
        return 2

    roles = None
    if args.roles:
        roles = [part.strip() for part in args.roles.split(",") if part.strip()]

    run = run_workflow(
        args.workflow,
        prompt,
        context_paths=args.context or None,
        roles=roles,
        repeats=args.repeat,
        max_workers=args.max_workers,
        runs_dir=None if args.no_save else Path(args.runs_dir),
    )
    if args.json:
        print(json.dumps(run.to_dict(), indent=2))
    else:
        print(run.markdown)
    return 0 if run.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
