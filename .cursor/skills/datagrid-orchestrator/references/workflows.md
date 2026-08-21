# Orchestrator workflows

## `utility_buyout_risks`

**Goal:** Critical risks when buying out an electrical / utility package.

**Parallel Datagrid roles:** `mentor`, `schedule`, `change_order`

**Local differential (Cursor):** attach buyout notes; dedupe specialty tables into one register.

```bash
.venv/bin/datagrid-agents orchestrate utility_buyout_risks \
  -p "Buying out elec utility package — top risks from lessons learned" \
  -c ./notes/utility-buyout.md
```

## `rfi_packet_qa`

**Goal:** Completeness / clarity check before an RFI goes out.

**Parallel Datagrid roles:** `deep_search`, `drawings_specs`, `drawing_revision`

**Local differential:** scans prompt/paths for RFI/drawing tokens and flags missing attachments.

```bash
.venv/bin/datagrid-agents orchestrate rfi_packet_qa \
  -p "Review RFI-12 against drawings A-101 and E-201" \
  -c ./packets/rfi-12/
```

When you build a dedicated RFI agent in Datagrid, set `DATAGRID_AGENT_RFI=<id>` (role `rfi` is already reserved) and/or add `rfi` to the workflow role list.

## `submittal_disposition`

**Goal:** Spec/drawing-based disposition notes for a submittal package.

**Parallel Datagrid roles:** `submittal`, `drawings_specs`, `deep_search`

**Local differential:** same attachment/token coverage helper as RFI QA.

```bash
.venv/bin/datagrid-agents orchestrate submittal_disposition \
  -p "Disposition submittal 03 30 00 concrete mix design" \
  -c ./submittals/033000/
```

## `lessons_multipass`

**Goal:** Run the Lessons Learned web-app extraction lenses in parallel (20 specialized passes).

**Parallel Datagrid roles:** `lessons_extractor` × 20 lens-scoped prompts

**Local context:** pass the interview Q&A / closeout notes via `-c`; the opening statement is `-p`.

Used by the web extract pipeline (`server/lessons_pipeline.py`) through `run_parallel` with progressive `on_result` events. Tune concurrency with `DATAGRID_ORCH_LESSONS_MAX_WORKERS` (default 20).

```bash
.venv/bin/datagrid-agents orchestrate lessons_multipass \
  -p "Utility buyout slipped late in Phase 2" \
  -c ./notes/interview.md
```

## `fanout` (new / custom agents)

Ad-hoc parallel calls for any registered roles. Use this for agents you just built (after adding them to `agents.yaml` or setting `DATAGRID_AGENT_<ROLE>`).

Supports calling the **same role multiple times** with `--repeat N` (distinct pass angles).

```bash
# New combo of existing roles
.venv/bin/datagrid-agents orchestrate fanout \
  --roles mentor,rfi,schedule \
  -p "What should we pressure-test before buyout?"

# Same agent, two passes
.venv/bin/datagrid-agents orchestrate fanout \
  --roles mentor \
  --repeat 2 \
  -p "First pass: underground risk. Second pass: commercial/contract risk."
```

## `compose` (natural-language DAG)

Compose a multi-stage DAG from a free-form goal, then execute stage-by-stage (parallel within a stage, sequenced by `depends_on`). Later stages can receive prior outputs (`include_prior`).

Planner modes:
- `heuristic` — local keyword/intent rules (fast, deterministic)
- `llm` — ask a Datagrid planner role (default `mentor`) for JSON DAG
- `auto` — heuristic first; use LLM when the goal looks multi-step/open-ended

```bash
# Plan only
.venv/bin/datagrid-agents compose \
  -p "Review RFI-12, then summarize lessons and schedule risk" \
  --mode auto \
  --plan-only

# Plan + execute
.venv/bin/datagrid-agents compose \
  -p "First gather drawing/spec evidence, then synthesize mentor + schedule risks" \
  -c ./packets/rfi-12 \
  --mode auto

# Force LLM planner
.venv/bin/datagrid-agents compose -p "..." --llm

# Execute a Cursor-edited DAG JSON
.venv/bin/datagrid-agents compose --dag ./plan.json
```

## Adding a named workflow

1. Create `src/datagrid_agents/orchestrator/workflows/<name>.py` with `build_calls(prompt, context)`.
2. Register it in `workflows/__init__.py`.
3. Document it here.
