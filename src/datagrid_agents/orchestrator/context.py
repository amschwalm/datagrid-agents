"""Gather local repository context to supplement Datagrid agent prompts."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_CHARS_PER_FILE = 8_000
DEFAULT_MAX_TOTAL_CHARS = 24_000


def gather_context(
    paths: list[Path | str] | None,
    *,
    max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """Read local files and return a prompt-ready context block."""
    if not paths:
        return ""

    chunks: list[str] = []
    total = 0
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            chunks.append(f"### Missing file: {path}\n(file not found)\n")
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    piece, total = _read_file_chunk(
                        child, max_chars_per_file, max_total_chars, total
                    )
                    if piece:
                        chunks.append(piece)
                    if total >= max_total_chars:
                        break
            if total >= max_total_chars:
                break
            continue

        piece, total = _read_file_chunk(
            path, max_chars_per_file, max_total_chars, total
        )
        if piece:
            chunks.append(piece)
        if total >= max_total_chars:
            break

    if not chunks:
        return ""
    return "## Local repository context\n\n" + "\n".join(chunks)


def _read_file_chunk(
    path: Path,
    max_chars_per_file: int,
    max_total_chars: int,
    total: int,
) -> tuple[str, int]:
    remaining = max_total_chars - total
    if remaining <= 0:
        return "", total
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"### {path}\n(unreadable: {exc})\n", total

    limit = min(max_chars_per_file, remaining)
    truncated = text[:limit]
    suffix = "\n…[truncated]\n" if len(text) > limit else "\n"
    chunk = f"### {path}\n```\n{truncated.rstrip()}\n```{suffix}"
    return chunk, total + len(truncated)
