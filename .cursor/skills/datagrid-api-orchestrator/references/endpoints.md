# Datagrid API endpoints

Base URL: `https://api.datagrid.com/v1` (`$DATAGRID_API_BASE` to override).
Auth: `Authorization: Bearer $DATAGRID_API_KEY`. Optional scope header:
`Datagrid-Teamspace: <id>`.

Docs: https://developers.datagrid.com

Use `DatagridClient.request(method, path, ...)` for anything not wrapped, or the
named methods in `scripts/datagrid_client.py`.

| Method | Path | Purpose | Client helper |
| --- | --- | --- | --- |
| GET | `/identity` | Authenticated user + teamspace memberships | `whoami()` |
| GET | `/organization/credits` | Current billing-period credits | `get_credits()` |
| GET | `/organization/teamspaces` | List org teamspaces | `list_teamspaces()` |
| POST | `/organization/teamspaces` | Create teamspace | `create_teamspace()` |
| GET | `/organization/teamspaces/{id}` | Retrieve teamspace | `get_teamspace()` |
| PATCH | `/organization/teamspaces/{id}` | Update teamspace | `request("PATCH", ...)` |
| GET | `/organization/teamspaces/{id}/users` | Teamspace members | `list_teamspace_users()` |
| PATCH | `/organization/teamspaces/{id}/users/{user_id}` | Update member | `request("PATCH", ...)` ⚠️ |
| DELETE | `/organization/teamspaces/{id}/users/{user_id}` | Remove member | `request("DELETE", ...)` ⚠️ |
| GET/POST | `/organization/teamspaces/{id}/invites` | List/create invites | `request(...)` ⚠️ |
| GET | `/organization/users` | Org users | `list_org_users()` |
| GET | `/organization/mcp-servers` | Org MCP servers | `list_mcp_servers()` |
| POST | `/converse` | Run an agent turn | `converse()` |
| GET | `/agents` | List agents | `list_agents()` |
| POST | `/agents` | Create agent | `create_agent()` |
| GET/PATCH/DELETE | `/agents/{id}` | Retrieve/update/delete | `get_agent` / `update_agent` / `delete_agent` |
| POST | `/agents/generate` | Generate agent from prompt | `generate_agent()` |
| POST | `/agents/claim` | Claim a generated agent | `claim_agent()` |
| GET | `/knowledge` | List knowledge (**key's home teamspace only**) | `list_knowledge()` |
| POST | `/knowledge` | Create knowledge | `create_knowledge()` |
| GET/PATCH/DELETE | `/knowledge/{id}` | Retrieve/update/delete | `get_knowledge` / `update_knowledge` / `delete_knowledge` |
| POST | `/knowledge/{id}/reindex` | Reindex | `reindex_knowledge()` |
| POST | `/knowledge/connect` | Connect a source | `connect_knowledge()` |
| GET | `/tables` | List tables (**not header-scoped**; filter by knowledge_id) | `list_tables()` |
| GET | `/tables/{id}` | Retrieve table | `get_table()` |
| GET | `/tables/{id}/records` | List records | `all_records()` |
| GET | `/files` | List files | `list_files()` |
| GET/PATCH/DELETE | `/files/{id}` | Retrieve/update/delete | `get_file` / `request` / `delete_file` |
| GET | `/files/{id}/content` | Download bytes | `request("GET", ...)` |
| GET | `/pages` | List pages | `list_pages()` |
| GET/POST/PATCH/DELETE | `/pages/{id}` | Page CRUD | `get_page` / `request` |
| POST | `/search/ai` | AI search (header-scoped) | `ai_search()` |
| GET | `/search/tree` | Search tree (header-scoped) | `search_tree()` |
| GET | `/search` | Deprecated keyword search | `search()` |
| GET | `/conversations` | List conversations | `list_conversations()` |
| GET/PATCH/DELETE | `/conversations/{id}` | Retrieve/update/delete | `get_conversation` / `request` / `delete_conversation` |
| GET | `/conversations/{id}/messages` | Messages | `list_messages()` |
| GET | `/tools` | List tools | `list_tools()` |
| GET | `/tools/{name}` | Retrieve tool | `get_tool()` |
| GET | `/connections` | Connections | `list_connections()` |
| GET | `/connectors` | Connectors | `list_connectors()` |
| GET | `/connection-providers` | Connection providers | `list_connection_providers()` |
| GET | `/secrets` | Secrets (metadata only) | `list_secrets()` |
| POST/DELETE | `/secrets` `/secrets/{id}` | Create/delete secret | `create_secret` / `delete_secret` |
| GET | `/webhooks` | List webhooks | `list_webhooks()` |
| POST/PATCH/DELETE | `/webhooks` `/webhooks/{id}` | Webhook CRUD | `create_webhook` / `delete_webhook` |
| GET | `/webhooks/active` | Active webhooks for an event | `request("GET", ...)` |
| GET | `/data-views` | Data views | `list_data_views()` |
| POST | `/batch-predictions` | Create batch | `create_batch_prediction()` |
| GET | `/batch-predictions` | List batches | `list_batch_predictions()` |
| GET | `/batch-predictions/{id}` | Retrieve | `get_batch_prediction()` |
| POST | `/batch-predictions/{id}/cancel` | Cancel | `cancel_batch_prediction()` |
| GET | `/batch-predictions/{id}/results` | Results | `request("GET", ...)` |
| GET | `/user-memories` | User memory | `list_memory()` |
| POST | `/voice` | Start voice session | `request("POST", ...)` ⚠️ |
| GET | `/voice-orchestrator/tasks` | Voice tasks | `request("GET", ...)` ⚠️ |
| POST | `/beta/rewrite` | Beta rewrite | `request("POST", ...)` ⚠️ |

⚠️ = REST-shaped helper; confirm the request body against
https://developers.datagrid.com before using create/update in production.

## Teamspace header vs query

Never send `teamspace` as a query or JSON field to `/knowledge` or `/tables`
(400: property should not exist). Pass `teamspace=` as a Python keyword so it
becomes the `Datagrid-Teamspace` header only. That header still does **not**
retarget `/knowledge` or `/tables`.
