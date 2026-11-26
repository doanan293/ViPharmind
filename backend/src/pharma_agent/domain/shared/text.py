"""Text helpers shared by the corpus and retrieval domains."""

import re
import unicodedata

ELLIPSIS = "…"
_WHITESPACE_RE = re.compile(r"\s+")
# Markdown block markers at the start of a line: headings, quotes, bullets, numbered items.
_BLOCK_MARKER_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)")
# Emphasis markers around words (**bold**, __bold__, *italic*, _italic_).
_EMPHASIS_RE = re.compile(
    r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1|(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\3(?![\w*])"
)


def normalize_text(text: str) -> str:
    """NFC, unify line endings, drop trailing spaces per line and outer blank lines."""
    unified = (
        unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    )
    lines = [line.rstrip() for line in unified.split("\n")]
    start = 0
    end = len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def _is_table_rule(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and "-" in stripped and not stripped.strip("|-: ")


def make_snippet(text: str, max_chars: int) -> str:
    """One-line preview: no table pipes or rules, no markdown markers, cut at a word boundary
    with "…"."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    kept = [
        _BLOCK_MARKER_RE.sub("", line)
        for line in text.splitlines()
        if not _is_table_rule(line)
    ]
    plain = _EMPHASIS_RE.sub(lambda m: m.group(2) or m.group(4), " ".join(kept))
    flat = _WHITESPACE_RE.sub(" ", plain.replace("|", " ")).strip()
    if len(flat) <= max_chars:
        return flat
    head = flat[: max_chars - 1]
    if flat[max_chars - 1] != " ":
        boundary = head.rfind(" ")
        if boundary > 0:
            head = head[:boundary]
    return head.rstrip() + ELLIPSIS
