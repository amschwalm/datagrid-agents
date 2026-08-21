"""Synthesize and dedupe agent findings into a ranked risk/checklist register."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from datagrid_agents.orchestrator.parallel import AgentResult

_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<c1>[^|]+?)\s*\|\s*(?P<c2>[^|]+?)\s*\|\s*(?P<c3>[^|]+?)(?:\s*\|\s*(?P<c4>[^|]+?))?\s*\|$"
)
_SEPARATOR_RE = re.compile(r"^\|\s*:?-{3,}")
_NEXT_ACTION_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*)?(?:recommended next action|next action|mentorship takeaway|your next)\b.*$"
)


@dataclass
class RegisterItem:
    """One deduped finding for the risk/checklist register."""

    title: str
    detail: str
    action: str
    sources: list[str] = field(default_factory=list)
    score: int = 0
    severity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Synthesis:
    """Structured synthesis of an orchestration run."""

    items: list[RegisterItem]
    next_actions: list[str]
    markdown: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "next_actions": list(self.next_actions),
            "markdown": self.markdown,
        }


def synthesize_results(
    results: list[AgentResult],
    *,
    prompt: str = "",
    workflow: str = "",
    max_items: int = 10,
) -> Synthesis:
    """Extract table rows, dedupe near-duplicates, and emit a ranked register."""
    raw_items: list[RegisterItem] = []
    next_actions: list[str] = []

    for result in results:
        if not result.ok or not result.text.strip():
            continue
        raw_items.extend(_extract_table_items(result.text, source=result.role))
        action = _extract_next_action(result.text)
        if action:
            next_actions.append(f"{result.role}: {action}")

    deduped = _dedupe_items(raw_items)
    ranked = sorted(deduped, key=lambda item: (-item.score, item.title.lower()))
    ranked = ranked[:max_items]
    markdown = _render_register(
        ranked,
        next_actions=next_actions,
        prompt=prompt,
        workflow=workflow,
    )
    return Synthesis(items=ranked, next_actions=next_actions, markdown=markdown)


def _extract_table_items(text: str, *, source: str) -> list[RegisterItem]:
    items: list[RegisterItem] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or _SEPARATOR_RE.match(stripped):
            continue
        match = _TABLE_ROW_RE.match(stripped)
        if not match:
            continue
        c1 = _clean_cell(match.group("c1"))
        c2 = _clean_cell(match.group("c2"))
        c3 = _clean_cell(match.group("c3"))
        c4 = _clean_cell(match.group("c4") or "")
        headerish = {c1.lower(), c2.lower(), c3.lower()}
        if headerish & {"risk", "finding", "item", "why it matters", "severity", "disposition"}:
            continue
        if c1.lower() in {"---", ":---", "---:"}:
            continue

        severity = _infer_severity(c1, c2, c3, c4)
        title = c1
        # Common shapes:
        # Risk | Why | Action
        # Finding | Severity | Evidence | Fix
        # Item | Disposition | Basis | Notes
        if c4:
            detail = f"{c2} | {c3}".strip(" |")
            action = c4
        else:
            detail = c2
            action = c3
        score = 1 + len(title) // 40
        if severity == "high":
            score += 5
        elif severity == "med":
            score += 3
        elif severity == "low":
            score += 1
        if any(token in (title + detail).lower() for token in ("critical", "stop-work", "safety")):
            score += 2
        items.append(
            RegisterItem(
                title=title,
                detail=detail,
                action=action,
                sources=[source],
                score=score,
                severity=severity,
            )
        )
    return items


def _extract_next_action(text: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _NEXT_ACTION_RE.search(line.strip()):
            # Prefer the following non-empty paragraph/bullet.
            for follow in lines[index + 1 : index + 6]:
                cleaned = follow.strip().lstrip("-* ").strip()
                if cleaned and not cleaned.startswith("#"):
                    return cleaned[:300]
            cleaned = re.sub(r"^.*?:\s*", "", line.strip())
            return cleaned[:300] if cleaned else None
    return None


def _infer_severity(*cells: str) -> str:
    blob = " ".join(cells).lower()
    if re.search(r"\b(high|critical|severe)\b", blob):
        return "high"
    if re.search(r"\b(med|medium|moderate)\b", blob):
        return "med"
    if re.search(r"\b(low|minor)\b", blob):
        return "low"
    return ""


def _clean_cell(value: str) -> str:
    text = value.strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    stop = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on"}
    tokens = [t for t in text.split() if t and t not in stop]
    return " ".join(tokens)


def _token_set(title: str) -> set[str]:
    normalized = _normalize_title(title)
    return {t for t in normalized.split() if len(t) > 2}


def _dedupe_items(items: list[RegisterItem]) -> list[RegisterItem]:
    clusters: list[RegisterItem] = []
    for item in items:
        merged = False
        item_tokens = _token_set(item.title)
        for existing in clusters:
            existing_tokens = _token_set(existing.title)
            if not item_tokens or not existing_tokens:
                continue
            overlap = len(item_tokens & existing_tokens) / max(
                1, len(item_tokens | existing_tokens)
            )
            if overlap >= 0.5 or _normalize_title(item.title) == _normalize_title(
                existing.title
            ):
                # Keep the richer title/detail; accumulate sources and score.
                if len(item.detail) > len(existing.detail):
                    existing.detail = item.detail
                if len(item.action) > len(existing.action):
                    existing.action = item.action
                if item.severity and not existing.severity:
                    existing.severity = item.severity
                for source in item.sources:
                    if source not in existing.sources:
                        existing.sources.append(source)
                existing.score += max(1, item.score // 2) + 2
                merged = True
                break
        if not merged:
            clusters.append(
                RegisterItem(
                    title=item.title,
                    detail=item.detail,
                    action=item.action,
                    sources=list(item.sources),
                    score=item.score,
                    severity=item.severity,
                )
            )
    return clusters


def _render_register(
    items: list[RegisterItem],
    *,
    next_actions: list[str],
    prompt: str,
    workflow: str,
) -> str:
    lines = [
        "# Risk / checklist register",
        "",
        f"- workflow: `{workflow or 'unknown'}`",
        f"- goal: {prompt.strip() or '(empty)'}",
        f"- items: {len(items)}",
        "",
        "## Ranked register",
        "",
        "| Rank | Item | Severity | Why / evidence | Action | Sources |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not items:
        lines.append("| 1 | (no table findings extracted) |  |  | Review agent narratives manually |  |")
    else:
        for index, item in enumerate(items, start=1):
            lines.append(
                "| {rank} | {title} | {severity} | {detail} | {action} | {sources} |".format(
                    rank=index,
                    title=_escape_cell(item.title),
                    severity=_escape_cell(item.severity or "n/a"),
                    detail=_escape_cell(item.detail),
                    action=_escape_cell(item.action),
                    sources=_escape_cell(", ".join(item.sources)),
                )
            )
    lines.extend(["", "## Checklist", ""])
    if items:
        for item in items:
            lines.append(f"- [ ] {item.title}: {item.action}")
    else:
        lines.append("- [ ] Review agent narratives and extract actions manually")
    if next_actions:
        lines.extend(["", "## Recommended next actions", ""])
        for action in next_actions:
            lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _escape_cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ").strip()
