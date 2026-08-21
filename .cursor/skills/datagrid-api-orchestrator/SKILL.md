---
name: datagrid-api-orchestrator
description: "Drive the Datagrid API — especially running MANY agent prompts CONCURRENTLY and recovering from long, flaky agent runs. Use whenever you want to talk to Datagrid agents in bulk, fan a prompt across several agents, run parallel conversations, retry agents that stall or say they couldn't retrieve the data, continue or resume Datagrid conversations, run AI search over a teamspace, pull knowledge/files/tables/records, list or create agents/teamspaces/webhooks, run batch predictions, or call any Datagrid (dg) endpoint. Trigger it when the user says run these prompts through an agent, spin up concurrent agents, test prompts on my Datagrid agent, search a teamspace's data, or names Datagrid, developers.datagrid.com, or an agent or teamspace by name. Prefer this over ad-hoc curl for anything Datagrid."
---

# Datagrid API Orchestrator

A complete, **self-contained, stdlib-only** toolkit for the Datagrid API with
first-class support for **running many agent prompts in parallel** and
**recovering from stalled agent runs**. Nothing to install and no external
dependencies — a single Python client wraps every endpoint, and two scripts drive
the concurrent explore → dispatch pipeline.

Fully generic: not tied to any organization, teamspace, or agent. Point it at any
Datagrid workspace with an API key and it works.

This repo also has `.cursor/skills/datagrid-orchestrator/` — that skill is the
**construction playbook** layer (`datagrid-agents orchestrate` / `compose`,
`agents.yaml` roles). Use **this** skill for generic API work, teamspace
explore, and concurrent converse with stall retries. Use the other skill for
named construction workflows (buyout risks, RFI QA, submittal disposition,
lessons multipass).

```
.cursor/skills/datagrid-api-orchestrator/
├── SKILL.md
├── scripts/
│   ├── datagrid_client.py   # client wrapping EVERY endpoint (import or CLI)
│   ├── explore.py           # STAGE 1: profile a teamspace (all knowledge + AI search sweep)
│   ├── orchestrate.py       # STAGE 3: concurrent runner: parallel prompts + retries
│   └── .env.example         # copy to .env and add your key (never commit the real key)
└── references/
    ├── endpoints.md         # every endpoint: method, path, purpose, doc link
    └── recipes.md           # a concrete action for every endpoint group
```

From the repo root, prefix commands with
`.cursor/skills/datagrid-api-orchestrator/` (examples below use `scripts/` as if
the cwd is this skill folder).

## Setup (do this first)

1. **API key.** Copy `scripts/.env.example` to `scripts/.env` and set
   `DATAGRID_API_KEY=...` (get one from the Datagrid dashboard → Settings → API
   keys). This repo also honors a root `.env` and `$Datagrid_API_KEY`. The client
   resolves the key in this order: `api_key=` arg → `$DATAGRID_API_KEY` →
   `$Datagrid_API_KEY` → the `.env` file. **Never print, echo, or paste the key
   into chat.** If a key ever leaks into a shell error/log, rotate it in the
   dashboard immediately. Base URL defaults to `https://api.datagrid.com/v1`;
   override with `$DATAGRID_API_BASE`.
2. **Python.** Any Python 3.8+ interpreter works — no pip installs needed (pure
   stdlib). If `python`/`python3` is shimmed by a wrapper that errors, fall back
   to `/usr/bin/python3`.
3. **Smoke test:** `python scripts/datagrid_client.py whoami` (also: `agents`,
   `teamspaces`, `credits`, `tools`). If it returns JSON, you're wired up.

## Core concept: teamspace scoping

Agents are organization-wide, but the DATA they read (uploaded docs, tables,
third-party connections) lives in a **teamspace**. Scope every agent call to the
right teamspace via the `Datagrid-Teamspace` header — the client does this when
you pass `teamspace=`, and the orchestrator resolves a teamspace *name* to its id
automatically. Getting this wrong is the #1 cause of "the agent can't see my
data." List teamspaces with `client.list_teamspaces()`.

Two exceptions: `list_knowledge()` and `list_tables()`. Pass `teamspace=` only as an
explicit keyword (never inside `**params`, or the API 400s with "property teamspace
should not exist") — but **the header does not retarget either endpoint**:

- `/knowledge` returns the knowledge of **the key's own teamspace**
  (`whoami()["current_teamspace_id"]`), whatever you pass. Scoped, but fixed — to
  read a different teamspace you need a key that sits in it.
- `/tables` isn't teamspace-confined at all; most rows' parent knowledge isn't even
  visible to the calling key. Scope it client-side by keeping tables whose
  `knowledge_id` is in `list_knowledge()`'s ids.

Never tell a user a `/knowledge` or `/tables` listing is "teamspace X's" because you
passed `teamspace=X`. `ai_search`/`search_tree` *are* header-scoped — use those.

## The full pipeline: explore → generate prompts → dispatch

The intended end-to-end flow when the user says "go through the data in teamspace
X and run targeted prompts across the agents." Do all three stages:

**Stage 1 — Explore (automated).** Profile the whole dataset so prompts are
grounded in what's actually there:
```bash
python scripts/explore.py --teamspace "My Teamspace" --out profile
```
This retrieves **all knowledge** (`list_knowledge` + `get_knowledge` per item),
inventories tables and agents, and runs an **AI-search sweep** (several broad
probes so the data is surfaced from multiple angles). Add your own domain-specific
probes with `--queries probes.txt` (one per line). It writes `profile/profile.md`
(read this), `profile/profile.json`, and a `profile/jobs_template.json` pre-filled
with the teamspace and every agent id.

**Stage 2 — Generate targeted prompts (you, reading the profile).** Read
`profile.md` and write concrete prompts that *name the real documents, tables, and
figures you found* — that grounding is what makes agent output land. Fill the
`prompt` fields in `jobs_template.json` (add/remove/duplicate jobs as needed; one
agent can get several prompts). Use the prompt patterns below. There's no
auto-generator on purpose: writing good targeted prompts from the findings is a
judgment step best done by the model running this skill.

**Stage 3 — Dispatch concurrently (automated).**
```bash
python scripts/orchestrate.py --jobs profile/jobs_template.json --out results --concurrency 6
```
Runs every prompt in parallel with retry-on-stall; writes `results/<tag>.md/.json`
and `results/SUMMARY.md`. Empty prompts in the template are skipped.

## Running many prompts concurrently (the main event)

Each `converse` call is a single long blocking request — often **several minutes**,
sometimes >15. So: **run them in parallel, and never wrap a long converse call in
a shell/subagent with a short timeout** (a 15-min cap will kill it mid-run). Use
`orchestrate.py`, which uses a thread pool and writes each result to disk as it
finishes.

**Fan one prompt across several agents:**
```bash
python scripts/orchestrate.py \
  --agents "Agent A,Agent B" \
  --prompt "analyze the project and summarize the top risks" \
  --teamspace "My Teamspace" \
  --out results --concurrency 6
```

**Run a batch of distinct jobs (recommended)** — write a `jobs.json` list, then:
```bash
python scripts/orchestrate.py --jobs jobs.json --out results --concurrency 6
```
Each job: `{"tag","agent"|"agent_id","prompt","teamspace"?,"conversation_id"?,"max_retries"?,"knowledge_ids"?}`.
See the header of `orchestrate.py` for the full job schema. Output: `results/<tag>.md`
+ `.json` per job and a `results/SUMMARY.md` table (tools, retries, stalled?,
credits, chars).

Concurrency guidance: 4–8 is a good default. Higher risks 429s (the client backs
off automatically, but throughput won't improve much past the rate limit).

## Retry-on-stall (built in — keep it on)

Datagrid agents sometimes **stop early and ask you to retry** — most often an
analysis agent stopping after schema/data retrieval and returning a "data gap"
framework with no real values. This is usually *behavioral, not a true data gap*:
the same agent returns full results on a directed follow-up.

`orchestrate.py` detects this (retry language + very few tool calls) and
**continues the same conversation** with an execution-forcing nudge, reusing the
schemas already loaded. Default 2 retries; tune with `--max-retries` or per-job
`max_retries`. If a run still stalls, the summary flags it `stalled=yes` so you
can escalate to a **narrower** prompt (see next section).

When you re-prompt by hand, the reliable nudges are:
- *"You stopped after retrieving schemas. Now EXECUTE the queries and return the
  actual values, each with its source. Don't return a framework or schema."*
- For incomplete lists: *"Don't use semantic search — list from the authoritative
  source/list API and return every row."*

## Prompt patterns that work

- **Analysis agents: narrow beats broad.** Single-focus prompts ("show unapproved
  change orders", "cost by category", "list overdue items") reliably pull numbers.
  Broad multi-part prompts ("budget + trends + exposure + margin in one")
  frequently stall — split them into separate jobs and stitch the results.
- **Log/extraction agents: specify the columns and the focus.** "Line-item log by
  category, cross-reference X→Y, cite the source link per item" produces a working
  log; a bare "make a log" gives a roll-up.
- **Name the documents — and attach them if the agent can't see them.** Agents read
  uploaded files (spec sheets, PDFs, narratives), not just structured tables —
  naming them surfaces data (lead times, discrepancies) that table queries miss.
  Use **AI search first** to discover what documents/records exist
  (`client.ai_search(...)`), then reference them in the prompt. **Important gotcha:**
  a teamspace knowledge item is only readable by an agent if it's in that agent's
  *corpus*. If an agent reports a document as "not found" even though `explore.py`
  lists it as `ready`, the doc exists but isn't attached to that agent — pass its id
  via the job's `knowledge_ids` (the orchestrator adds it to `config.corpus` for the
  call). This is the usual root cause of "value: Not provided". Get the ids from
  `profile.json`.
- **Verify figures.** Agent-reported numbers can vary run-to-run; treat outputs as
  drafts and reconcile against the source system before external use. When drafting
  an artifact for the user to copy out, prefix its title with `[AI-DRAFT]`.

## Using the client directly for everything else

For non-converse work, import the client and call the method for the endpoint. It
covers **every** Datagrid endpoint group — see `references/endpoints.md` for the
full list (method, path, doc link) and `references/recipes.md` for a concrete
action per group (AI search, retrieve/create knowledge, files, tables & records,
batch predictions, connections, conversations, pages, secrets, webhooks, memory,
data views, MCP servers, teamspaces & users, tools, credits, identity).

```python
import sys; sys.path.insert(0, "scripts")
from datagrid_client import DatagridClient
c = DatagridClient(teamspace="My Teamspace")   # name or id or leave unset

c.ai_search("what long-lead items and lead times exist?")           # AI search
c.list_knowledge(); c.get_knowledge(kid); c.reindex_knowledge(kid)  # knowledge
for rec in c.all_records(table_id): ...                             # paginate records
c.create_batch_prediction(model="...", items=[...], prompt="...", output_schema={...})
c.get_credits()                                                     # billing
```

Any endpoint not wrapped, or a path you want to confirm, is reachable via
`c.request("GET", "/some/path", params={...})`. A handful of sub-resource paths in
the client follow REST convention rather than a verified doc example — these are
marked ⚠️ in `references/endpoints.md`; confirm the request body against the
linked doc before relying on a create/update in production.

## Letting agents run as long as they need (don't time out)

Agent runs are long and variable — minutes, sometimes much more. Two independent
timeouts can cut them off; handle both:

1. **The HTTP call timeout** (inside the client). Default is 60 min per converse
   call (`DATAGRID_CONVERSE_TIMEOUT` seconds to change). For exceptionally long
   jobs raise it, e.g. `DATAGRID_CONVERSE_TIMEOUT=7200 python scripts/orchestrate.py …`.
   The client also auto-retries transient 429/5xx/network drops with backoff.
2. **The launcher's timeout** (the shell/tool that STARTS the orchestrator). A
   foreground call often caps at ~10–15 min, which kills long runs mid-flight. So
   **launch the orchestrator detached** and poll its output files — never hold it
   open in a short-timeout foreground call:
   ```bash
   nohup python scripts/orchestrate.py --jobs profile/jobs_template.json \
     --out results --concurrency 6 > results/run.log 2>&1 &
   ```
   Then watch `results/run.log` and the per-job `results/<tag>.json` files as they
   appear. Because each job writes the moment it finishes, a slow agent never
   blocks the others and partial progress is always on disk.

## Operational notes

- **Long runs:** background heavy jobs and poll their result files; don't hold a
  short-timeout foreground call open. The orchestrator writes each `<tag>.json`
  the moment that job finishes, so progress is visible incrementally.
- **Idempotency & cost:** `converse`, `ai_search`, and batch predictions consume
  credits; check `c.get_credits()` if you're running a large fan-out. Don't re-run
  completed jobs — resume by reading the existing result files.
- **Destructive endpoints** (delete agent/knowledge/conversation/teamspace/…) are
  wrapped but should be confirmed with the user before calling.
- **Security:** the API key is the only secret this skill needs. Keep `.env` out of
  version control, never echo the key, and use Datagrid **secrets** (`create_secret`
  + `secret_ids` in converse) for any credentials an agent needs at runtime rather
  than putting them in prompts.
- **Drop-in scripts:** if you have a fuller `datagrid_client.py` / `explore.py` /
  `orchestrate.py`, replace the files in `scripts/`. Keep the CLI entry points
  (`whoami`, `--jobs`, `--teamspace`) so this skill still runs.
