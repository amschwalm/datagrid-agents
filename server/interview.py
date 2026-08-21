"""Helpers for dynamic interview / follow-up question generation."""

from __future__ import annotations

import json
import re
from typing import Any


# Scope-narrowing defaults if the model fails to return JSON.
DEFAULT_FOLLOWUPS: list[str] = [
    "Which phase, package, or time window should we prioritize in this project's knowledge?",
    "Which artifact types should we weight most heavily (RFIs, meetings, change events, submittals, daily reports, schedule)?",
    "What kinds of lessons matter most here — cost, schedule, quality, safety, buyout, or closeout?",
    "How should we confirm a lesson is real — recurrence across sources, named stakeholders, or documented impact?",
    "Are there topics or areas we should deliberately exclude from this extraction?",
]


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


def parse_reasoning_steps(text: str) -> list[dict[str, str]]:
    """Best-effort extraction of reasoning_steps from a model JSON payload."""
    raw = (text or "").strip()
    if not raw:
        return []
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        steps = data.get("reasoning_steps") or data.get("reasoning") or []
        if not isinstance(steps, list):
            continue
        out: list[dict[str, str]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            label = str(step.get("label") or "").strip()
            if not label:
                continue
            out.append(
                {
                    "id": str(step.get("id") or f"step-{len(out)+1}"),
                    "label": label,
                    "status": str(step.get("status") or "done"),
                    "detail": str(step.get("detail") or "").strip(),
                }
            )
        if out:
            return out
    return []
