"""CLI for managing construction Datagrid agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from datagrid_agents.client import MissingApiKeyError
from datagrid_agents.orchestrator import list_roles
from datagrid_agents.orchestrator.skill_bridge import load_skill_modules, skill_scripts_dir
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


def cmd_orchestrate(args: argparse.Namespace) -> int:
    """Dispatch through the stdlib skill orchestrator (jobs.json or --agents)."""
    _, orch_mod = load_skill_modules()
    argv: list[str] = []
    if args.jobs:
        argv.extend(["--jobs", args.jobs])
    if args.agents:
        argv.extend(["--agents", args.agents])
    if args.prompt:
        argv.extend(["--prompt", args.prompt])
    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
        argv.extend(["--prompt", prompt])
    if args.teamspace:
        argv.extend(["--teamspace", args.teamspace])
    argv.extend(["--out", args.out])
    argv.extend(["--concurrency", str(args.concurrency)])
    argv.extend(["--max-retries", str(args.max_retries)])
    try:
        return orch_mod.main(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1


def cmd_explore(args: argparse.Namespace) -> int:
    import importlib

    scripts = str(skill_scripts_dir())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    explore = importlib.import_module("explore")
    argv = ["--teamspace", args.teamspace, "--out", args.out]
    if args.queries:
        argv.extend(["--queries", args.queries])
    try:
        return explore.main(argv)
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1


def cmd_whoami(_: argparse.Namespace) -> int:
    client_mod, _ = load_skill_modules()
    client = client_mod.DatagridClient()
    json.dump(client.whoami(), sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


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

    p_whoami = sub.add_parser("whoami", help="Show Datagrid identity for this API key")
    p_whoami.set_defaults(func=cmd_whoami)

    p_explore = sub.add_parser(
        "explore",
        help="Profile a teamspace (knowledge, tables, agents, AI-search sweep)",
    )
    p_explore.add_argument("--teamspace", "-t", required=True, help="Teamspace name or id")
    p_explore.add_argument("--out", default="profile", help="Output directory")
    p_explore.add_argument("--queries", help="Optional extra AI-search probes file")
    p_explore.set_defaults(func=cmd_explore)

    p_orch = sub.add_parser(
        "orchestrate",
        help="Run concurrent Datagrid converse jobs (stdlib skill orchestrator)",
    )
    p_orch.add_argument("--jobs", help="jobs.json (list or {jobs:[...]})")
    p_orch.add_argument("--agents", help="Comma-separated agent names/ids (with --prompt)")
    p_orch.add_argument("--prompt", "-p", help="Shared prompt when using --agents")
    p_orch.add_argument("--file", "-f", help="Read prompt from a file")
    p_orch.add_argument("--teamspace", "-t", help="Default teamspace name or id")
    p_orch.add_argument("--out", default="results", help="Output directory")
    p_orch.add_argument("--concurrency", type=int, default=6)
    p_orch.add_argument("--max-retries", type=int, default=2)
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
