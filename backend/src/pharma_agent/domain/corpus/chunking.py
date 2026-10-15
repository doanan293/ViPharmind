"""The single corpus chunker (spec v2 §3.0c).

Public API. A chunk is the unit the model reads: consecutive sections of one document
packed to about ``TARGET_CHUNK_CHARS``, or one part of a section longer than
``MAX_CHUNK_CHARS``. Splitting of long text is ported from pharma-lab
``split_lines_without_breaking_entries`` and ``split_long_text``; tables follow the
leaflet ``split_table`` header rule.
"""

import re
import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.corpus.bundle import (
    BlockKind,
    ColloquialMappingRecord,
    DocumentRecord,
    GlossaryEntry,
    SectionRecord,
)
from pharma_agent.domain.corpus.enrichment import (
    compose_embedding_text,
    detect_terms,
    mapping_for_section,
)
from pharma_agent.domain.corpus.identity import chunk_version_id, sha256_hex
from pharma_agent.domain.retrieval.models import ColloquialMapping, TermAnnotation

CHUNKER_VERSION = "chunker-v2"
# A chunk grows by whole sections until the next one would pass this; packed chunks
# average about 1,000 Qwen3 tokens on the corpus (measured, spec v2 §3.0c).
TARGET_CHUNK_CHARS = 4200
# A single section longer than this is split on its own. Tables and lists take more
# tokens per character than prose, so the longest chunk reaches about 3,200 tokens,
# inside the 4,096-token embedding slot and rerank ubatch.
MAX_CHUNK_CHARS = 5600

_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")
_SENTENCE_END_RE = re.compile(r"[.!?;:…]\s+")
_LAST_WORD_RE = re.compile(r"\s+\S*$")


class ChunkDraft(BaseModel):
    """One chunk of a document: whole consecutive sections, or one part of a long section."""

    model_config = ConfigDict(frozen=True)

    chunk_version_id: uuid.UUID
    document_key: str
    ordinal: int
    section_keys: list[str]
    headings: list[str]
    chunk_text: str
    context_header: str
    embedding_text: str
    embedding_text_sha256: str
    start_page: int | None
    end_page: int | None
    term_annotations: list[TermAnnotation]
    colloquial: ColloquialMapping | None


def split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Cut at the last sentence end, else newline, else whitespace, else hard."""
    parts: list[str] = []
    remaining = paragraph.strip()
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]
        split_at = -1
        sentence_ends = list(_SENTENCE_END_RE.finditer(window))
        if sentence_ends:
            split_at = sentence_ends[-1].end()
        if split_at <= 0:
            newline_at = window.rfind("\n", 0, max_chars + 1)
            if newline_at > 0:
                split_at = newline_at + 1
        if split_at <= 0:
            last_word = _LAST_WORD_RE.search(window)
            if last_word and last_word.start() > 0:
                split_at = last_word.start()
        if split_at <= 0:
            split_at = max_chars
        chunk = remaining[:split_at].strip()
        if chunk:
            parts.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def split_long_text(text: str, max_chars: int) -> list[str]:
    """Pack blank-line separated paragraphs; text that fits is returned as is."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_BREAK_RE.split(text)
        if paragraph.strip()
    ]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        chunks.extend(split_oversized_paragraph(paragraph, max_chars))
    if current:
        chunks.append(current)
    return chunks


def split_table_markdown(markdown: str, max_chars: int) -> list[str]:
    """Split rows into parts that each repeat the table's first two rows.

    The first two rows are the header whether or not the second one is a separator, because
    leaflet tables often spread their header over several rows. A part is closed before it
    reaches ``max_chars``. Text without two leading table rows is split as prose.
    """
    text = markdown.strip()
    if len(text) <= max_chars:
        return [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or not all(line.startswith("|") for line in lines[:2]):
        return split_long_text(text, max_chars)
    header = "\n".join(lines[:2])
    chunks: list[str] = []
    rows: list[str] = []
    length = len(header)
    for row in lines[2:]:
        if rows and length + 1 + len(row) >= max_chars:
            chunks.append("\n".join([header, *rows]))
            rows = []
            length = len(header)
        rows.append(row)
        length += 1 + len(row)
    if rows:
        chunks.append("\n".join([header, *rows]))
    return chunks


def split_lines_without_breaking_entries(text: str, max_chars: int) -> list[str]:
    """Pack lines; a line starting lowercase continues the entry above it."""
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate = "\n".join([*current, line]) if current else line
        if current and len(candidate) > max_chars:
            next_lines = [line]
            while current and next_lines[0][:1].islower():
                next_lines.insert(0, current.pop())
            if current:
                chunks.append("\n".join(current))
            current = next_lines
            continue
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _split_block(kind: BlockKind, text: str, max_chars: int) -> list[str]:
    if kind is BlockKind.TABLE:
        return split_table_markdown(text, max_chars)
    if kind is BlockKind.LIST or kind is BlockKind.INDEX_ENTRIES:
        return split_lines_without_breaking_entries(text, max_chars)
    return split_long_text(text, max_chars)


def section_text(section: SectionRecord) -> str:
    """The section as the model reads it: its heading, then its blocks; empty when blank."""
    body = "\n\n".join(b.markdown.strip() for b in section.blocks if b.markdown.strip())
    if not body:
        return ""
    heading = section.heading.strip()
    return f"## {heading}\n\n{body}" if heading else body


def _context_header(title: str, headings: Sequence[str]) -> str:
    names = [h.strip() for h in headings if h.strip()]
    title_text = title.strip()
    if title_text and names:
        return f"{title_text} > {'; '.join(names)}"
    return title_text or "; ".join(names)


def _pages(sections: Sequence[SectionRecord]) -> tuple[int | None, int | None]:
    starts = [s.start_page for s in sections if s.start_page is not None]
    ends = [s.end_page for s in sections if s.end_page is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _section_parts(section: SectionRecord, max_chars: int) -> list[str]:
    """A long section as several texts, each under max_chars and each led by the heading.

    Blocks too long on their own are split first; the pieces are then packed in order, so a
    lead-in sentence stays with the table it introduces and no part is a lone fragment.
    """
    heading = f"## {section.heading.strip()}\n\n" if section.heading.strip() else ""
    budget = max_chars - len(heading)
    pieces: list[str] = []
    for block in section.blocks:
        raw = block.markdown.strip()
        if raw:
            pieces.extend(_split_block(block.kind, raw, budget))
    parts: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if current and len(candidate) > budget:
            parts.append(current)
            candidate = piece
        current = candidate
    if current:
        parts.append(current)
    return [heading + part for part in parts]


def chunk_document(
    document: DocumentRecord,
    sections: Sequence[SectionRecord],
    glossary: Sequence[GlossaryEntry],
    mappings: Sequence[ColloquialMappingRecord],
    *,
    target_chars: int = TARGET_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[ChunkDraft]:
    """Pack a document's sections, in order, into chunks of about target_chars."""
    groups: list[tuple[list[SectionRecord], str]] = []
    current: list[SectionRecord] = []
    current_text = ""

    def flush() -> None:
        nonlocal current, current_text
        if current:
            groups.append((current, current_text))
        current, current_text = [], ""

    for section in sorted(sections, key=lambda s: s.ordinal):
        text = section_text(section)
        if not text:
            continue
        if len(text) > max_chars:
            flush()
            groups.extend(
                ([section], part) for part in _section_parts(section, max_chars)
            )
            continue
        if current and len(current_text) + 2 + len(text) > target_chars:
            flush()
        current_text = f"{current_text}\n\n{text}" if current_text else text
        current.append(section)
    flush()

    drafts: list[ChunkDraft] = []
    for ordinal, (members, chunk_text) in enumerate(groups, start=1):
        headings = [member.heading for member in members]
        context_header = _context_header(document.title, headings)
        colloquial = next(
            (
                mapping
                for mapping in (mapping_for_section(m.key, mappings) for m in members)
                if mapping is not None
            ),
            None,
        )
        searchable = (
            f"{context_header}\n\n{chunk_text}" if context_header else chunk_text
        )
        terms = detect_terms(searchable, glossary)
        embedding_text = compose_embedding_text(
            context_header=context_header,
            chunk_text=chunk_text,
            colloquial=colloquial,
            terms=terms,
        )
        start_page, end_page = _pages(members)
        drafts.append(
            ChunkDraft(
                chunk_version_id=chunk_version_id(
                    document.key, chunk_text, embedding_text, CHUNKER_VERSION
                ),
                document_key=document.key,
                ordinal=ordinal,
                section_keys=[member.key for member in members],
                headings=headings,
                chunk_text=chunk_text,
                context_header=context_header,
                embedding_text=embedding_text,
                embedding_text_sha256=sha256_hex(embedding_text),
                start_page=start_page,
                end_page=end_page,
                term_annotations=terms,
                colloquial=colloquial,
            )
        )
    return drafts
