# Orchestrator agent roles

Source of truth: `src/datagrid_agents/orchestrator/agents.yaml`

Override any role id with `DATAGRID_AGENT_<ROLE>` (example: `DATAGRID_AGENT_MENTOR` or `DATAGRID_AGENT_RFI`).

| Key | Specialty | Typical use |
| --- | --- | --- |
| `mentor` | Lessons learned | Buyout pitfalls, historical risk patterns |
| `schedule` | Schedule risk | Lead times, utility coordination delays, CP impact |
| `change_order` | Change orders | Documentation/pricing gaps that become COs |
| `deep_search` | Project search | Specs/drawings/RFI/submittal grounded answers |
| `drawings_specs` | Drawings & specs | Callouts, materials, annotation search |
| `drawing_revision` | Drawing revisions | Revision conflicts and coordination gaps |
| `submittal` | Submittal review | Spec vs product compliance |
| `rfi` | RFI review (alias) | Reserved for a dedicated RFI agent; defaults to deep_search until overridden |

## Adding a new Datagrid agent

1. Build/test the agent in Datagrid UI.
2. Copy its ID into `agents.yaml` under a new role key **or** export `DATAGRID_AGENT_<ROLE>=<id>`.
3. Call it immediately via:
   - `datagrid-agents orchestrate fanout --roles <role> -p "..."`  
   - or `datagrid-agents run <agent_id> -p "..."`
4. Optionally add the role to a named workflow’s `ROLES` tuple.

List live mapping:

```bash
.venv/bin/datagrid-agents roles
```
