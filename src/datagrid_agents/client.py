"""Datagrid client helpers."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from datagrid_ai import Datagrid


class MissingApiKeyError(RuntimeError):
    """Raised when DATAGRID_API_KEY is not configured."""


def load_env() -> None:
    """Load environment variables from a local .env file if present."""
    load_dotenv(override=False)


def require_api_key() -> str:
    """Return the Datagrid API key or raise a clear error."""
    load_env()
    api_key = os.environ.get("DATAGRID_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        raise MissingApiKeyError(
            "Set DATAGRID_API_KEY in your environment or .env file. "
            "Create a key at https://app.datagrid.com (API Keys)."
        )
    return api_key


@lru_cache(maxsize=1)
def get_client() -> Datagrid:
    """Return a cached Datagrid client authenticated with DATAGRID_API_KEY."""
    return Datagrid(api_key=require_api_key())
