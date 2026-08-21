"""Shared JSON extraction helpers for agent responses."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> Any | None:
    raw = (text or "").strip()
    if not raw:
        return None

    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end > start:
            candidates.append(raw[start : end + 1])

    candidates.append(raw)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None
