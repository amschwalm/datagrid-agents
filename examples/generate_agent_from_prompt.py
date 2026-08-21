"""Use Datagrid's generate → claim → create flow for a new construction agent.

This is useful when you want a first draft of instructions/tools from a
natural-language description, then refine and persist the agent.

Usage:
  export DATAGRID_API_KEY=...
  python examples/generate_agent_from_prompt.py "An agent that reviews punch lists"
"""

from __future__ import annotations

import sys

from datagrid_agents.client import get_client


def main() -> None:
    prompt = " ".join(sys.argv[1:]).strip() or (
        "An agent that reviews construction punch lists, groups items by trade, "
        "and flags safety-related incomplete work."
    )
    client = get_client()

    generated = client.agents.generate(prompt=prompt)
    print(f"Generated template claim_token: {generated.claim_token}")

    template = client.agents.claim(claim_token=generated.claim_token)
    tools = []
    config = getattr(template, "config", None)
    if config and getattr(config, "tools", None):
        tools = [t.tool for t in config.tools]

    agent = client.agents.create(
        name=getattr(template, "title", None) or "Generated Construction Agent",
        system_prompt=getattr(config, "prompt", None),
        custom_prompt=getattr(config, "custom_prompt", None),
        tools=tools or None,
        agent_model="magpie-2.5",
    )
    print(f"Created agent: {agent.id} ({agent.name})")


if __name__ == "__main__":
    main()
