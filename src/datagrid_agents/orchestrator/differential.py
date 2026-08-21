"""Local Cursor-side analysis that supplements Datagrid agent judgment."""

from __future__ import annotations

import re
from pathlib import Path

# Common construction drawing/sheet tokens, e.g. A-101, E201, S-3.1
DRAWING_TOKEN_RE = re.compile(
    r"\b(?:RFI[- ]?\d+|[A-Z]{1,3}-?\d{1,4}(?:\.\d+)?[A-Z]?)\b",
    re.IGNORECASE,
)


def analyze_attachment_coverage(
    prompt: str,
    context_paths: list[Path | str] | None,
) -> str:
    """Compare tokens mentioned in the prompt/paths against attached local files."""
    paths = [Path(p) for p in (context_paths or [])]
    existing_files: list[Path] = []
    missing_paths: list[Path] = []
    for path in paths:
        if path.is_file():
            existing_files.append(path)
        elif path.is_dir():
            existing_files.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        else:
            missing_paths.append(path)

    haystack = prompt + "\n" + "\n".join(str(p) for p in paths)
    tokens = sorted({m.group(0).upper() for m in DRAWING_TOKEN_RE.finditer(haystack)})
    file_names = {p.name.upper() for p in existing_files}
    file_stems = {p.stem.upper() for p in existing_files}

    matched: list[str] = []
    unmatched: list[str] = []
    for token in tokens:
        normalized = token.upper().replace(" ", "")
        hit = any(
            normalized in name or normalized in stem or token.upper() in name
            for name, stem in zip(file_names, file_stems)
        )
        (matched if hit else unmatched).append(token)

    lines = [
        "## Local differential analysis",
        "",
        f"- Attached files found: {len(existing_files)}",
        f"- Missing paths: {len(missing_paths)}",
        f"- Referenced tokens scanned: {len(tokens)}",
    ]
    if missing_paths:
        lines.append("- Missing: " + ", ".join(str(p) for p in missing_paths))
    if matched:
        lines.append("- Tokens with a local file match: " + ", ".join(matched))
    if unmatched:
        lines.append(
            "- Tokens without an obvious local file match: " + ", ".join(unmatched)
        )
        lines.append(
            "- Action: attach the missing drawings/specs before relying on completeness claims."
        )
    if not tokens:
        lines.append(
            "- No RFI/drawing-like tokens detected in the prompt or context paths."
        )
    lines.append("")
    return "\n".join(lines)
