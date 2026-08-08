"""CLI for managing construction Datagrid agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from datagrid_agents.client import MissingApiKeyError
from datagrid_agents.orchestrator import list_roles, list_workflows, run_workflow
from datagrid_agents.registry import list_definitions, load_definition
from datagrid_agents import service


def _print_definition(definition) -> None:
    tools = ", ".join(definition.tools) if definition.tools else "(default tools)"
    print(f"{definition.slug}")
    print(f"  name:    {definition.name}")
    print(f"  model:   {definition.agent_model}")
    print(f"  tools:   {tools}")
    print(f"  about:   {definition.description}")


def cmd_list_local(_: argparse.Namespace) -> int:
    definitions = list_definitions()
    if not definitions:
        print("No local agent definitions found.")
        return 0
    for definition in definitions:
        _print_definition(definition)
        print()
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    definition = load_definition(args.slug)
    _print_definition(definition)
    print()
    print("system_prompt:")
    print(definition.system_prompt)
    if definition.custom_prompt:
        print("\ncustom_prompt:")
        print(definition.custom_prompt)
    if definition.planning_prompt:
        print("\nplanning_prompt:")
        print(definition.planning_prompt)
    if definition.sample_prompt:
        print("\nsample_prompt:")
        print(definition.sample_prompt)
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    slugs = args.slug or None
    created = service.create_all(slugs=slugs, state_path=Path(args.state))
    for slug, agent in created.items():
        print(f"created {slug} -> {agent.id}")
    print(f"saved IDs to {args.state}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    slugs = args.slug or None
    synced = service.sync_all(slugs=slugs, state_path=Path(args.state))
    for slug, agent in synced.items():
        print(f"synced {slug} -> {agent.id}")
    print(f"saved IDs to {args.state}")
    return 0


def cmd_list_remote(args: argparse.Namespace) -> int:
    agents = service.list_remote_agents(search=args.search)
    if not agents:
        print("No remote agents found.")
        return 0
    for agent in agents:
        desc = getattr(agent, "description", None) or ""
        print(f"{agent.id}\t{agent.name}\t{desc}")
    return 0


def cmd_roles(_: argparse.Namespace) -> int:
    roles = list_roles()
    if not roles:
        print("No orchestrator roles configured.")
        return 0
    for role in roles:
        print(f"{role.key}\t{role.id}\t{role.name}\t{role.role}\t{role.chat_mode}")
    return 0


def cmd_workflows(_: argparse.Namespace) -> int:
    names = list_workflows()
    if not names:
        print("No orchestrator workflows registered.")
        return 0
    for name in names:
        print(name)
    return 0


def cmd_orchestrate(args: argparse.Namespace) -> int:
    prompt = args.prompt
    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    if not prompt:
        print("Provide --prompt or --file.", file=sys.stderr)
        return 2

    roles = None
    if args.roles:
        roles = [part.strip() for part in args.roles.split(",") if part.strip()]
        if not roles:
            print("error: --roles was empty", file=sys.stderr)
            return 2

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


def cmd_run(args: argparse.Namespace) -> int:
    prompt = args.prompt
    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    if not prompt:
        definition = None
        try:
            definition = load_definition(args.agent)
        except FileNotFoundError:
            pass
        if definition and definition.sample_prompt:
            prompt = definition.sample_prompt
            print(f"(using sample prompt from {definition.slug})\n", file=sys.stderr)
        else:
            print("Provide --prompt or --file, or use a slug with a sample_prompt.", file=sys.stderr)
            return 2

    response = service.converse_with_agent(
        args.agent,
        prompt,
        chat_mode=args.chat_mode,
        conversation_id=args.conversation_id,
        state_path=Path(args.state),
    )
    text = service.response_text(response)
    if args.json:
        payload = {
            "agent": args.agent,
            "conversation_id": getattr(response, "conversation_id", None),
            "text": text,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(text)
        conversation_id = getattr(response, "conversation_id", None)
        if conversation_id:
            print(f"\n[conversation_id={conversation_id}]", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datagrid-agents",
        description="Create and run construction AI agents on the Datagrid API.",
    )
    parser.add_argument(
        "--state",
        default=str(service.DEFAULT_STATE_PATH),
        help="Path to local slug->agent_id JSON map (default: ./.agent_ids.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List local construction agent definitions")
    p_list.set_defaults(func=cmd_list_local)

    p_show = sub.add_parser("show", help="Show one local agent definition")
    p_show.add_argument("slug", help="Definition slug, e.g. rfi_reviewer")
    p_show.set_defaults(func=cmd_show)

    p_create = sub.add_parser("create", help="Create agents in Datagrid from local definitions")
    p_create.add_argument(
        "slug",
        nargs="*",
        help="Optional definition slugs (default: all)",
    )
    p_create.set_defaults(func=cmd_create)

    p_sync = sub.add_parser(
        "sync",
        help="Create or update Datagrid agents from local definitions",
    )
    p_sync.add_argument(
        "slug",
        nargs="*",
        help="Optional definition slugs (default: all)",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_remote = sub.add_parser("remote", help="List agents already in your Datagrid org")
    p_remote.add_argument("--search", help="Optional name search filter")
    p_remote.set_defaults(func=cmd_list_remote)

    p_run = sub.add_parser("run", help="Converse with a created agent")
    p_run.add_argument("agent", help="Local slug or Datagrid agent ID")
    p_run.add_argument("--prompt", "-p", help="Prompt text")
    p_run.add_argument("--file", "-f", help="Read prompt from a file")
    p_run.add_argument(
        "--chat-mode",
        default="full_agent",
        choices=["full_agent", "light_agent", "llm_router", "auto"],
        help="Datagrid converse chat_mode (default: full_agent)",
    )
    p_run.add_argument("--conversation-id", help="Continue an existing conversation")
    p_run.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    p_run.set_defaults(func=cmd_run)

    p_roles = sub.add_parser(
        "roles",
        help="List orchestrator role → Datagrid agent mappings",
    )
    p_roles.set_defaults(func=cmd_roles)

    p_workflows = sub.add_parser(
        "workflows",
        help="List named Cursor/Datagrid orchestration playbooks",
    )
    p_workflows.set_defaults(func=cmd_workflows)

    p_orch = sub.add_parser(
        "orchestrate",
        help="Run a parallel Datagrid + local-context orchestration workflow",
    )
    p_orch.add_argument(
        "workflow",
        help="Workflow name (see: datagrid-agents workflows)",
    )
    p_orch.add_argument("--prompt", "-p", help="Prompt / user goal text")
    p_orch.add_argument("--file", "-f", help="Read prompt from a file")
    p_orch.add_argument(
        "--context",
        "-c",
        action="append",
        default=[],
        help="Local file or directory to attach as code/context (repeatable)",
    )
    p_orch.add_argument(
        "--roles",
        help="Comma-separated role keys for the fanout workflow (e.g. mentor,schedule,rfi)",
    )
    p_orch.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="For fanout: call each role N times with distinct pass angles (default: 1)",
    )
    p_orch.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="Max parallel Datagrid calls (default: 3)",
    )
    p_orch.add_argument(
        "--runs-dir",
        default=".orchestrator/runs",
        help="Directory for run artifacts (default: .orchestrator/runs)",
    )
    p_orch.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write run artifacts to disk",
    )
    p_orch.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of markdown",
    )
    p_orch.set_defaults(func=cmd_orchestrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MissingApiKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
