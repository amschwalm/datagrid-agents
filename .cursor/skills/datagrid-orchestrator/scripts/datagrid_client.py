#!/usr/bin/env python3
"""Stdlib-only Datagrid API client (import or CLI).

No pip installs. Resolves the API key from (in order):
  api_key= argument → $DATAGRID_API_KEY → $Datagrid_API_KEY → scripts/.env → repo .env

Never print the API key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Iterator

DEFAULT_BASE = "https://api.datagrid.com/v1"
DEFAULT_CONVERSE_TIMEOUT = 3600
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Endpoints where `teamspace` must never appear in query/body (API 400s).
_NO_TEAMSPACE_PARAM = frozenset({"/knowledge", "/tables"})


class DatagridError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def _load_dotenv_files() -> None:
    """Load scripts/.env then repo-root .env without overriding existing env."""
    # scripts/ → skill → skills → .cursor → repo root
    repo_root = _scripts_dir()
    for _ in range(4):
        repo_root = repo_root.parent
    candidates = [
        _scripts_dir() / ".env",
        repo_root / ".env",
        Path.cwd() / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def resolve_api_key(api_key: str | None = None) -> str:
    _load_dotenv_files()
    key = (
        (api_key or "").strip()
        or os.environ.get("DATAGRID_API_KEY", "").strip()
        or os.environ.get("Datagrid_API_KEY", "").strip()
    )
    if not key or key == "your_api_key_here":
        raise DatagridError(
            "Set DATAGRID_API_KEY (environment or scripts/.env). "
            "Create a key at https://app.datagrid.com (API Keys)."
        )
    return key


def _json_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="replace")


class DatagridClient:
    """Thin urllib wrapper around every Datagrid v1 endpoint group."""

    def __init__(
        self,
        api_key: str | None = None,
        teamspace: str | None = None,
        base_url: str | None = None,
        converse_timeout: float | None = None,
    ) -> None:
        self.api_key = resolve_api_key(api_key)
        self.base_url = (
            (base_url or os.environ.get("DATAGRID_API_BASE") or DEFAULT_BASE)
            .rstrip("/")
        )
        self._teamspace_arg = teamspace or os.environ.get("DATAGRID_TEAMSPACE_ID") or None
        self._teamspace_id: str | None = (
            self._teamspace_arg.strip()
            if self._teamspace_arg and UUID_RE.match(self._teamspace_arg.strip())
            else None
        )
        self._resolving_teamspace = False
        self.converse_timeout = float(
            converse_timeout
            if converse_timeout is not None
            else os.environ.get("DATAGRID_CONVERSE_TIMEOUT", DEFAULT_CONVERSE_TIMEOUT)
        )

    # ----- HTTP -------------------------------------------------------------

    def _headers(self, teamspace_id: str | None, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "datagrid-orchestrator/1.0",
        }
        if teamspace_id:
            headers["Datagrid-Teamspace"] = teamspace_id
        if extra:
            headers.update(extra)
        return headers

    def resolve_teamspace(self, name_or_id: str | None = None) -> str | None:
        """Return a teamspace id. Names are matched case-insensitively."""
        value = name_or_id if name_or_id is not None else self._teamspace_arg
        if not value:
            return None
        value = str(value).strip()
        if not value:
            return None
        if UUID_RE.match(value):
            return value
        self._resolving_teamspace = True
        try:
            spaces = list(self.iter_list("/organization/teamspaces", teamspace=None))
        finally:
            self._resolving_teamspace = False
        needle = value.lower()
        matches = [s for s in spaces if (s.get("name") or "").strip().lower() == needle]
        if not matches:
            partial = [s for s in spaces if needle in (s.get("name") or "").lower()]
            names = ", ".join((s.get("name") or s.get("id") or "?") for s in (partial or spaces)[:12])
            raise DatagridError(f"No teamspace named {value!r}. Known: {names}")
        if len(matches) > 1:
            ids = ", ".join(s.get("id", "?") for s in matches)
            raise DatagridError(f"Teamspace name {value!r} is ambiguous ({ids}). Pass the id.")
        return matches[0]["id"]

    def _effective_teamspace(self, teamspace: str | None) -> str | None:
        if teamspace:
            return self.resolve_teamspace(teamspace)
        if self._resolving_teamspace:
            return None
        if self._teamspace_id:
            return self._teamspace_id
        if self._teamspace_arg:
            self._teamspace_id = self.resolve_teamspace(self._teamspace_arg)
            return self._teamspace_id
        return None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        teamspace: str | None = None,
        timeout: float | None = None,
        extra_headers: dict[str, str] | None = None,
        retries: int = 5,
    ) -> Any:
        """Call any path. `teamspace=` sets Datagrid-Teamspace; it is not sent as a query param."""
        if not path.startswith("/"):
            path = "/" + path
        params = dict(params or {})
        # Guard: never smuggle teamspace into query/body for endpoints that 400 on it.
        params.pop("teamspace", None)
        if json_body is not None and isinstance(json_body, dict):
            json_body = dict(json_body)
            if path.rstrip("/") in _NO_TEAMSPACE_PARAM:
                json_body.pop("teamspace", None)

        ts = self._effective_teamspace(teamspace)
        url = self.base_url + path
        if params:
            # drop Nones
            q = {k: v for k, v in params.items() if v is not None}
            if q:
                url += "?" + urllib.parse.urlencode(
                    {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in q.items()}
                )

        data = None
        headers = self._headers(ts, extra_headers)
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        wait = 1.0
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            try:
                with urllib.request.urlopen(req, timeout=timeout or 60) as resp:
                    return _json_body(resp.read())
            except urllib.error.HTTPError as exc:
                body = _json_body(exc.read())
                status = exc.code
                if status in {429, 500, 502, 503, 504} and attempt < retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        sleep_for = float(retry_after) if retry_after else wait
                    except (TypeError, ValueError):
                        sleep_for = wait
                    time.sleep(min(sleep_for, 60))
                    wait = min(wait * 2, 30)
                    last_err = DatagridError(
                        f"HTTP {status} {method.upper()} {path}", status=status, body=body
                    )
                    continue
                raise DatagridError(
                    f"HTTP {status} {method.upper()} {path}: {body}",
                    status=status,
                    body=body,
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < retries:
                    time.sleep(wait)
                    wait = min(wait * 2, 30)
                    last_err = exc
                    continue
                raise DatagridError(f"Network error {method.upper()} {path}: {exc}") from exc
        raise last_err or DatagridError(f"Request failed {method.upper()} {path}")

    def iter_list(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        teamspace: str | None = None,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("limit", limit)
        after = params.pop("after", None)
        while True:
            page_params = dict(params)
            if after:
                page_params["after"] = after
            page = self.request("GET", path, params=page_params, teamspace=teamspace)
            if isinstance(page, list):
                items = page
                has_more = False
            elif isinstance(page, dict):
                items = page.get("data") or page.get("items") or []
                has_more = bool(page.get("has_more"))
            else:
                return
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            if not has_more:
                return
            after = items[-1].get("id") if isinstance(items[-1], dict) else None
            if not after:
                return

    def all_list(self, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self.iter_list(path, **kwargs))

    # ----- identity / org ---------------------------------------------------

    def whoami(self) -> dict[str, Any]:
        return self.request("GET", "/identity", teamspace=None)

    def get_credits(self) -> dict[str, Any]:
        return self.request("GET", "/organization/credits")

    def list_teamspaces(self) -> list[dict[str, Any]]:
        return self.all_list("/organization/teamspaces", teamspace=None)

    def get_teamspace(self, teamspace_id: str) -> dict[str, Any]:
        return self.request("GET", f"/organization/teamspaces/{teamspace_id}")

    def create_teamspace(self, *, name: str, access: str = "closed", **body: Any) -> dict[str, Any]:
        payload = {"name": name, "access": access, **body}
        return self.request("POST", "/organization/teamspaces", json_body=payload)

    def list_org_users(self) -> list[dict[str, Any]]:
        return self.all_list("/organization/users")

    def list_teamspace_users(self, teamspace_id: str) -> list[dict[str, Any]]:
        return self.all_list(f"/organization/teamspaces/{teamspace_id}/users")

    def list_mcp_servers(self) -> list[dict[str, Any]]:
        return self.all_list("/organization/mcp-servers")

    # ----- agents / converse ------------------------------------------------

    def list_agents(self, search: str | None = None, teamspace: str | None = None) -> list[dict[str, Any]]:
        params = {"search": search} if search else None
        return self.all_list("/agents", params=params, teamspace=teamspace)

    def get_agent(self, agent_id: str, teamspace: str | None = None) -> dict[str, Any]:
        return self.request("GET", f"/agents/{agent_id}", teamspace=teamspace)

    def create_agent(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/agents", json_body=body)

    def update_agent(self, agent_id: str, **body: Any) -> dict[str, Any]:
        return self.request("PATCH", f"/agents/{agent_id}", json_body=body)

    def delete_agent(self, agent_id: str) -> Any:
        return self.request("DELETE", f"/agents/{agent_id}")

    def generate_agent(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/agents/generate", json_body=body)

    def claim_agent(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/agents/claim", json_body=body)

    def find_agent(self, name_or_id: str, teamspace: str | None = None) -> dict[str, Any]:
        if UUID_RE.match(name_or_id.strip()):
            return self.get_agent(name_or_id.strip(), teamspace=teamspace)
        needle = name_or_id.strip().lower()
        agents = self.list_agents(teamspace=teamspace)
        exact = [a for a in agents if (a.get("name") or "").strip().lower() == needle]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            ids = ", ".join(a.get("id", "?") for a in exact)
            raise DatagridError(f"Agent name {name_or_id!r} is ambiguous ({ids}). Pass the id.")
        partial = [a for a in agents if needle in (a.get("name") or "").lower()]
        if len(partial) == 1:
            return partial[0]
        names = ", ".join((a.get("name") or a.get("id") or "?") for a in agents[:15])
        raise DatagridError(f"No agent named {name_or_id!r}. Known: {names}")

    def converse(
        self,
        prompt: str,
        *,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        chat_mode: str = "full_agent",
        teamspace: str | None = None,
        knowledge_ids: Iterable[str] | None = None,
        config: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"prompt": prompt, "chat_mode": chat_mode}
        if agent_id:
            body["agent_id"] = agent_id
        if conversation_id:
            body["conversation_id"] = conversation_id
        cfg = dict(config or {})
        kids = [k for k in (knowledge_ids or []) if k]
        if kids:
            existing = list(cfg.get("corpus") or [])
            have = {item.get("knowledge_id") for item in existing if isinstance(item, dict)}
            for kid in kids:
                if kid not in have:
                    existing.append({"type": "knowledge", "knowledge_id": kid})
            cfg["corpus"] = existing
        if cfg:
            body["config"] = cfg
        if extra:
            body.update(extra)
        return self.request(
            "POST",
            "/converse",
            json_body=body,
            teamspace=teamspace,
            timeout=timeout if timeout is not None else self.converse_timeout,
        )

    @staticmethod
    def converse_text(response: Any) -> str:
        if not isinstance(response, dict):
            return str(response or "").strip()
        parts: list[str] = []
        for item in response.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "\n".join(parts).strip()
        for key in ("output_text", "text", "message"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    @staticmethod
    def converse_credits(response: Any) -> float | None:
        if not isinstance(response, dict):
            return None
        credits = response.get("credits")
        if isinstance(credits, dict):
            consumed = credits.get("consumed")
        else:
            consumed = credits
        try:
            return float(consumed) if consumed is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def converse_tool_calls(response: Any) -> list[Any]:
        if not isinstance(response, dict):
            return []
        return list(response.get("tool_calls") or [])

    # ----- knowledge / files / tables --------------------------------------

    def list_knowledge(self, *, teamspace: str | None = None, **params: Any) -> list[dict[str, Any]]:
        # teamspace= is accepted as an explicit kw (sets header) but never as a query param.
        params.pop("teamspace", None)
        return self.all_list("/knowledge", params=params or None, teamspace=teamspace)

    def get_knowledge(self, knowledge_id: str, teamspace: str | None = None) -> dict[str, Any]:
        return self.request("GET", f"/knowledge/{knowledge_id}", teamspace=teamspace)

    def create_knowledge(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/knowledge", json_body=body)

    def update_knowledge(self, knowledge_id: str, **body: Any) -> dict[str, Any]:
        return self.request("PATCH", f"/knowledge/{knowledge_id}", json_body=body)

    def delete_knowledge(self, knowledge_id: str) -> Any:
        return self.request("DELETE", f"/knowledge/{knowledge_id}")

    def reindex_knowledge(self, knowledge_id: str) -> Any:
        return self.request("POST", f"/knowledge/{knowledge_id}/reindex")

    def connect_knowledge(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/knowledge/connect", json_body=body)

    def list_tables(self, *, teamspace: str | None = None, **params: Any) -> list[dict[str, Any]]:
        params.pop("teamspace", None)
        return self.all_list("/tables", params=params or None, teamspace=teamspace)

    def get_table(self, table_id: str) -> dict[str, Any]:
        return self.request("GET", f"/tables/{table_id}")

    def list_records(self, table_id: str, **params: Any) -> list[dict[str, Any]]:
        return self.all_list(f"/tables/{table_id}/records", params=params or None)

    def all_records(self, table_id: str, **params: Any) -> list[dict[str, Any]]:
        return self.list_records(table_id, **params)

    def list_files(self, teamspace: str | None = None) -> list[dict[str, Any]]:
        return self.all_list("/files", teamspace=teamspace)

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self.request("GET", f"/files/{file_id}")

    def delete_file(self, file_id: str) -> Any:
        return self.request("DELETE", f"/files/{file_id}")

    def list_pages(self, teamspace: str | None = None) -> list[dict[str, Any]]:
        return self.all_list("/pages", teamspace=teamspace)

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self.request("GET", f"/pages/{page_id}")

    # ----- search -----------------------------------------------------------

    def ai_search(
        self,
        query: str,
        *,
        teamspace: str | None = None,
        limit: int | None = None,
        record_types: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if limit is not None:
            body["limit"] = limit
        if record_types:
            body["record_types"] = record_types
        return self.request("POST", "/search/ai", json_body=body, teamspace=teamspace)

    def search_tree(self, query: str, *, teamspace: str | None = None, **body: Any) -> dict[str, Any]:
        payload = {"query": query, **body}
        return self.request("GET", "/search/tree", params=payload, teamspace=teamspace)

    def search(self, query: str, *, teamspace: str | None = None, **params: Any) -> dict[str, Any]:
        payload = {"query": query, **params}
        return self.request("GET", "/search", params=payload, teamspace=teamspace)

    # ----- conversations / webhooks / misc ---------------------------------

    def list_conversations(self, teamspace: str | None = None) -> list[dict[str, Any]]:
        return self.all_list("/conversations", teamspace=teamspace)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.request("GET", f"/conversations/{conversation_id}")

    def delete_conversation(self, conversation_id: str) -> Any:
        return self.request("DELETE", f"/conversations/{conversation_id}")

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self.all_list(f"/conversations/{conversation_id}/messages")

    def list_webhooks(self) -> list[dict[str, Any]]:
        return self.all_list("/webhooks")

    def create_webhook(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/webhooks", json_body=body)

    def delete_webhook(self, webhook_id: str) -> Any:
        return self.request("DELETE", f"/webhooks/{webhook_id}")

    def list_secrets(self) -> list[dict[str, Any]]:
        return self.all_list("/secrets")

    def create_secret(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/secrets", json_body=body)

    def delete_secret(self, secret_id: str) -> Any:
        return self.request("DELETE", f"/secrets/{secret_id}")

    def list_tools(self) -> list[dict[str, Any]]:
        page = self.request("GET", "/tools")
        if isinstance(page, dict):
            return list(page.get("data") or page.get("items") or [])
        if isinstance(page, list):
            return page
        return []

    def get_tool(self, tool_name: str) -> dict[str, Any]:
        return self.request("GET", f"/tools/{urllib.parse.quote(tool_name)}")

    def list_connections(self) -> list[dict[str, Any]]:
        return self.all_list("/connections")

    def list_connectors(self) -> list[dict[str, Any]]:
        return self.all_list("/connectors")

    def list_connection_providers(self) -> list[dict[str, Any]]:
        return self.all_list("/connection-providers")

    def list_data_views(self) -> list[dict[str, Any]]:
        return self.all_list("/data-views")

    def create_batch_prediction(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/batch-predictions", json_body=body)

    def get_batch_prediction(self, batch_id: str) -> dict[str, Any]:
        return self.request("GET", f"/batch-predictions/{batch_id}")

    def list_batch_predictions(self) -> list[dict[str, Any]]:
        return self.all_list("/batch-predictions")

    def cancel_batch_prediction(self, batch_id: str) -> Any:
        return self.request("POST", f"/batch-predictions/{batch_id}/cancel")

    def list_memory(self) -> list[dict[str, Any]]:
        return self.all_list("/user-memories")


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Datagrid API client (stdlib).")
    parser.add_argument(
        "command",
        nargs="?",
        default="whoami",
        help="whoami | agents | teamspaces | credits | tools | knowledge",
    )
    parser.add_argument("--teamspace", "-t", help="Teamspace name or id (Datagrid-Teamspace header)")
    parser.add_argument("--search", help="Optional search filter (agents)")
    parser.add_argument("--json", action="store_true", help="Force JSON even for empty results")
    args = parser.parse_args(argv)

    client = DatagridClient(teamspace=args.teamspace)
    command = args.command.lower().strip()
    if command in {"whoami", "identity", "me"}:
        payload: Any = client.whoami()
    elif command in {"agents", "agent"}:
        payload = client.list_agents(search=args.search, teamspace=args.teamspace)
    elif command in {"teamspaces", "teamspace"}:
        payload = client.list_teamspaces()
    elif command in {"credits", "credit"}:
        payload = client.get_credits()
    elif command in {"tools", "tool"}:
        payload = client.list_tools()
    elif command in {"knowledge", "knowledges"}:
        payload = client.list_knowledge(teamspace=args.teamspace)
    else:
        print(f"Unknown command {args.command!r}. Try: whoami, agents, teamspaces, credits, tools.", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except DatagridError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
