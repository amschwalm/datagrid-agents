"""Create the RFI reviewer agent (if needed) and run its sample prompt.

Usage:
  export DATAGRID_API_KEY=...
  python examples/create_and_run_rfi_agent.py
"""

from __future__ import annotations

from datagrid_agents.registry import load_definition
from datagrid_agents import service


def main() -> None:
    definition = load_definition("rfi_reviewer")
    agent = service.sync_agent(definition)
    print(f"Agent ready: {agent.id} ({agent.name})")

    prompt = definition.sample_prompt or "Review an incomplete RFI for missing info."
    response = service.converse_with_agent(definition.slug, prompt, chat_mode="full_agent")
    print("\n--- Response ---\n")
    print(service.response_text(response))


if __name__ == "__main__":
    main()
