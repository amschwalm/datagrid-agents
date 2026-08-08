# datagrid-agents

Construction-focused AI agents built on the [Datagrid API](https://developers.datagrid.com).

This repo gives you ready-made agent blueprints (RFI review, submittals, safety, schedule risk, daily reports, change orders), a small Python CLI to create/sync them in your Datagrid workspace, and examples for running prompts through Converse.

## Prerequisites

1. A Datagrid account and API key from [app.datagrid.com](https://app.datagrid.com) (API Keys).
2. Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env and set DATAGRID_API_KEY
```

Optional: set `CONSTRUCTION_KNOWLEDGE_IDS` to a comma-separated list of Datagrid knowledge IDs so agents are scoped to your project docs instead of all org knowledge.

## Quick start

List the local construction agent blueprints:

```bash
datagrid-agents list
# or: python -m datagrid_agents.cli list
```

Create them in your Datagrid organization (IDs are saved to `.agent_ids.json`):

```bash
datagrid-agents create
# or one agent:
datagrid-agents create rfi_reviewer
```

Run an agent (uses the definition's sample prompt if you omit `--prompt`):

```bash
datagrid-agents run rfi_reviewer
datagrid-agents run rfi_reviewer -p "Review RFI-12 for missing drawing references."
```

Update agents after editing YAML definitions:

```bash
datagrid-agents sync
```

List agents already in Datagrid:

```bash
datagrid-agents remote
```

## Cursor orchestrator (Datagrid API + local code)

Build agents in Datagrid, then coordinate them from Cursor:

```bash
datagrid-agents roles
datagrid-agents workflows
datagrid-agents orchestrate utility_buyout_risks \
  -p "Buying out elec utility package — top risks from lessons learned" \
  -c ./notes/utility-buyout.md

# Other playbooks
datagrid-agents orchestrate rfi_packet_qa -p "Review RFI-12" -c ./packets/rfi-12
datagrid-agents orchestrate submittal_disposition -p "Disposition 03 30 00" -c ./submittals/033000

# New/custom agents (register in agents.yaml or DATAGRID_AGENT_<ROLE>)
datagrid-agents orchestrate fanout --roles mentor,rfi --repeat 1 -p "Pressure-test this buyout"
# Same agent, multiple passes:
datagrid-agents orchestrate fanout --roles mentor --repeat 2 -p "Pass 1 underground; pass 2 commercial"

# Natural-language DAG composition (plan and/or execute multi-stage graphs)
datagrid-agents compose -p "Review RFI-12, then synthesize mentor + schedule risks" --plan-only
datagrid-agents compose -p "First gather drawing evidence, then synthesize risks" --mode auto
datagrid-agents compose --dag ./plan.json
```

Named playbooks fan out parallel Datagrid converse calls, attach local file context, run lightweight local differential checks where relevant, and write artifacts under `.orchestrator/runs/`. `compose` builds a multi-stage DAG from natural language (heuristic and/or LLM planner).

Hardening defaults:
- budgets via `--max-workers` / `--timeout` / `--max-calls` (or `DATAGRID_ORCH_*` env)
- converse result cache in `.orchestrator/cache` (`--no-cache` to disable)
- synthesized risk/checklist register in `.orchestrator/registers/` (`--no-register` to skip)
- compose can continue `conversation_id` across stages for the same agent

Cursor skill: `.cursor/skills/datagrid-orchestrator/` (`/datagrid-orchestrator`).

Cursor subagent: `.cursor/agents/datagrid.md` — use the **datagrid** agent / `/datagrid` so chats route construction/knowledge work through the orchestrator.

Role IDs live in `src/datagrid_agents/orchestrator/agents.yaml` (override with `DATAGRID_AGENT_<ROLE>`).

## Included agents

| Slug | Use case |
| --- | --- |
| `rfi_reviewer` | Completeness / clarity checks before RFIs go to design |
| `submittal_checker` | Spec vs product data review and disposition notes |
| `safety_observer` | Hazard spotting from reports/photos with corrective actions |
| `schedule_risk` | Critical-path and delay risk analysis |
| `daily_report_summarizer` | Field report → PM/owner summary |
| `change_order_analyst` | COR documentation and pricing gap review |

Definitions live in `src/datagrid_agents/definitions/*.yaml`. Each file sets:

- `system_prompt` — role and scope
- `custom_prompt` — response format
- `planning_prompt` — multi-step approach
- `tools` — Datagrid tools (e.g. `semantic_search`, `pdf_extraction`)
- `agent_model` — defaults to `magpie-2.5` (Execute tier)

## Add your own agent

1. Copy an existing YAML file in `src/datagrid_agents/definitions/`.
2. Change the filename slug, name, prompts, and tools.
3. Run `datagrid-agents sync <slug>`.
4. Run `datagrid-agents run <slug> -p "..."`.

Or draft from natural language with Datagrid's generate flow:

```bash
python examples/generate_agent_from_prompt.py "An agent that reviews punch lists by trade"
```

## Examples

- `examples/create_and_run_rfi_agent.py` — sync + converse for the RFI agent
- `examples/generate_agent_from_prompt.py` — generate → claim → create

## Project layout

```text
src/datagrid_agents/
  cli.py                 # datagrid-agents command
  client.py              # Datagrid SDK helper
  registry.py            # load YAML definitions
  service.py             # create / sync / converse
  definitions/           # construction agent blueprints
  orchestrator/          # parallel Datagrid + local-context workflows
.cursor/skills/
  datagrid-orchestrator/ # Cursor skill for hybrid orchestration
examples/
tests/
```

## Tips for production use

- Scope knowledge with `corpus` / `CONSTRUCTION_KNOWLEDGE_IDS` so agents only read project documents.
- Prefer least-privilege tools; start narrow and add `pdf_extraction`, `data_analysis`, etc. only when needed.
- Use `chat_mode=full_agent` for multi-step tool work; use `light_agent` for faster RAG-style answers.
- Iterate prompts the same way you iterate code: run real RFIs/submittals, then refine YAML and `sync`.

## Docs

- [Datagrid quickstart](https://developers.datagrid.com/introduction/quickstart)
- [Getting started with Agents](https://developers.datagrid.com/api-reference/agents/agents)
- [Agent best practices](https://developers.datagrid.com/api-reference/agents/agent-best-practices)
- [Converse](https://developers.datagrid.com/api-reference/converse/converse-getting-started)
- Python SDK: [`datagrid_ai`](https://github.com/DatagridAI/datagrid-python)

## Tests

```bash
pip install -e ".[dev]"
pytest
```
