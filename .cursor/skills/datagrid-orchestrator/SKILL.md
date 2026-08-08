---
name: datagrid-orchestrator
description: Orchestrate parallel Datagrid API agent calls with local repository context and Cursor-only operations. Use when coordinating Datagrid agents, running hybrid construction workflows (buyout risks, RFI/submittal review), or combining knowledge-search agents with code/file analysis.
---

# Datagrid Orchestrator

Cursor owns planning, parallelism, local code context, and repo operations.
Datagrid agents own domain judgment and knowledge search.

## When to use

- User wants multiple Datagrid agents consulted in parallel
- A construction workflow needs lessons learned + schedule + change-order views
- Local files/code should supplement Datagrid prompts
- Follow-on work must happen in the repo (write checklist, open PR, run tests)
- The **datagrid** Cursor subagent (`.cursor/agents/datagrid.md`) is active — it should always load this skill

## Quick commands

From the repo root (venv recommended):

```bash
export DATAGRID_API_KEY="${DATAGRID_API_KEY:-$Datagrid_API_KEY}"
.venv/bin/datagrid-agents roles
.venv/bin/datagrid-agents workflows
.venv/bin/datagrid-agents orchestrate utility_buyout_risks \
  -p "<user goal>" \
  -c path/to/local/context
```

Named playbooks: `utility_buyout_risks`, `rfi_packet_qa`, `submittal_disposition`.

For **new agents** or custom combos (including calling the same agent multiple times):

```bash
.venv/bin/datagrid-agents orchestrate fanout \
  --roles mentor,rfi,schedule \
  --repeat 1 \
  -p "<user goal>"
```

For **natural-language DAG composition** (multi-stage, prior outputs fed forward):

```bash
.venv/bin/datagrid-agents compose \
  -p "Review RFI-12, then synthesize mentor + schedule risks" \
  --mode auto
```

Or use the skill wrapper:

```bash
python .cursor/skills/datagrid-orchestrator/scripts/run_workflow.py \
  utility_buyout_risks \
  -p "<user goal>" \
  -c path/to/file
```

## Operating procedure

1. **Clarify the goal** — package/trade, decision needed, and any local files.
2. **Pick a path**
   - Named playbook when it fits (`utility_buyout_risks`, `rfi_packet_qa`, `submittal_disposition`)
   - `fanout --roles ...` for explicit role lists / repeats
   - `compose -p "..."` for open-ended or multi-step natural-language goals (DAG)
3. **For compose goals** — optionally `--plan-only` first, edit the DAG JSON if needed, then `compose --dag plan.json`.
4. **Register new agents** — add to `agents.yaml` or set `DATAGRID_AGENT_<ROLE>`; then use `fanout` or include the role in a composed DAG.
5. **Attach local context** — use `-c` for notes, packets, schedule snippets, or open questions.
6. **Run orchestration** — `datagrid-agents orchestrate <workflow>` or `datagrid-agents compose ...`.
7. **Synthesize** — read merged markdown/JSON under `.orchestrator/runs/`. Deduplicate findings across agents/stages.
8. **Differential Cursor ops** — after Datagrid returns:
   - write a checklist or risk register into the repo
   - compare claims against local files
   - run tests/scripts
   - open a PR with artifacts
9. **Follow up** — reuse `conversation_id` values from the run JSON when continuing with one agent. Multi-pass same-agent: `fanout --roles mentor --repeat 2`.

## Guardrails

- Do **not** recreate Datagrid agents from Cursor unless the user asks; IDs live in `src/datagrid_agents/orchestrator/agents.yaml`.
- Prefer role keys (`mentor`, `schedule`, `change_order`) over hardcoding UUIDs in chat.
- Cap parallelism/budgets: `--max-workers`, `--timeout`, `--max-calls` (or env `DATAGRID_ORCH_*`).
- Result cache is on by default (`.orchestrator/cache`); use `--no-cache` to bypass.
- Risk/checklist register is written by default to `.orchestrator/registers/`; use `--no-register` to skip.
- Never print API keys.
- For expensive runs, prefer saving artifacts (`orchestrate` / `compose` do this by default).

## References

- Role registry details: `references/agents.md`
- Workflow catalog: `references/workflows.md`
