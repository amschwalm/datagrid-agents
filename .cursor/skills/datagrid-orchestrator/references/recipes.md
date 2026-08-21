# Recipes (one concrete action per endpoint group)

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
from datagrid_client import DatagridClient
c = DatagridClient(teamspace="My Teamspace")  # name or id
```

## Identity / credits / tools

```python
me = c.whoami()
print(me["user_id"], me["current_teamspace_id"], len(me["teamspaces"]))
print(c.get_credits())
for tool in c.list_tools():
    print(tool.get("name") or tool.get("id"))
```

CLI: `python scripts/datagrid_client.py whoami|credits|tools`

## Teamspaces

```python
for ts in c.list_teamspaces():
    print(ts["id"], ts.get("name"), ts.get("access"))
# Resolve a name to an id (also happens automatically on DatagridClient(teamspace="Name"))
ts_id = c.resolve_teamspace("KSA Demo")
```

Destructive: do not create/delete teamspaces unless the user asks.

## Agents

```python
agents = c.list_agents()
agent = c.find_agent("Mentor Agent")          # name or uuid
detail = c.get_agent(agent["id"])
```

Create/update/delete only when the user explicitly asks. Prefer iterating
prompts in the Datagrid UI.

## Converse (single turn)

```python
resp = c.converse(
    "List unapproved change orders with source citations.",
    agent_id=agent["id"],
    teamspace="My Teamspace",
    knowledge_ids=["<knowledge-id>"],   # optional corpus attach
)
print(c.converse_text(resp), c.converse_credits(resp), resp.get("conversation_id"))
```

Continue the same conversation:

```python
resp2 = c.converse(
    "Now return every row, not a summary.",
    agent_id=agent["id"],
    conversation_id=resp["conversation_id"],
)
```

For many prompts, use `scripts/orchestrate.py` instead of a loop in chat.

## Knowledge / files / pages

```python
# NOTE: this is the KEY's home teamspace, not an arbitrary header target.
items = c.list_knowledge()
kid = items[0]["id"]
meta = c.get_knowledge(kid)
# c.reindex_knowledge(kid)          # confirm with user; consumes credits
# c.delete_knowledge(kid)           # destructive
```

## Tables & records

```python
home_ids = {k["id"] for k in c.list_knowledge()}
tables = [t for t in c.list_tables() if t.get("knowledge_id") in home_ids]
for rec in c.all_records(tables[0]["id"]):
    print(rec.get("id"))
```

## AI search (header-scoped — this IS teamspace-aware)

```python
ans = c.ai_search("what long-lead items and lead times exist?", teamspace="My Teamspace")
tree = c.search_tree("change orders", teamspace="My Teamspace")
```

## Conversations

```python
for conv in c.list_conversations():
    print(conv["id"], conv.get("title") or conv.get("generated_title"))
# c.delete_conversation(conv_id)  # destructive — confirm first
```

## Connections / connectors / providers

```python
c.list_connectors()
c.list_connection_providers()
c.list_connections()
```

## Secrets

Use Datagrid secrets for runtime credentials. Never put secrets in prompts.

```python
# c.create_secret(name="erp", value=...)   # confirm with user
# then pass secret_ids=[...] into converse extra=
```

## Webhooks

```python
c.list_webhooks()
# c.create_webhook(url="https://...", events=[...])  # confirm with user
```

## Batch predictions

```python
# batch = c.create_batch_prediction(model="...", items=[...], prompt="...", output_schema={...})
# c.get_batch_prediction(batch["id"])
```

Consumes credits. Prefer a small trial batch first.

## Data views / MCP / memory / voice

```python
c.list_data_views()
c.list_mcp_servers()
c.list_memory()
```

Voice and beta rewrite: `c.request("POST", "/voice", json_body=...)` — confirm
the body against https://developers.datagrid.com first.

## Explore → dispatch pipeline

```bash
python scripts/explore.py --teamspace "My Teamspace" --out profile
# edit profile/jobs_template.json prompts
python scripts/orchestrate.py --jobs profile/jobs_template.json --out results --concurrency 6
```
