"""Helpers for dynamic interview / follow-up question generation."""

from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_FOLLOWUPS: dict[str, list[str]] = {
    "lessons": [
        "What project, phase, or workstream is this about?",
        "What actually happened versus what was planned?",
        "What drove the biggest cost, schedule, quality, or safety impact?",
        "Where did coordination or handoffs break down?",
        "What should the next team know on day one?",
    ],
    "mentor": [
        "What decision or problem do you need help with right now?",
        "What constraints are fixed (budget, contract, politics, schedule)?",
        "What have you already tried?",
        "What happens if this goes poorly in the next 30 days?",
        "What would a good outcome look like?",
    ],
}


def parse_questions(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []

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
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        questions: list[Any]
        if isinstance(data, list):
            questions = data
        elif isinstance(data, dict):
            questions = data.get("questions") or data.get("followups") or []
        else:
            continue
        cleaned = [str(q).strip() for q in questions if str(q).strip()]
        if cleaned:
            return cleaned[:8]
    return []
