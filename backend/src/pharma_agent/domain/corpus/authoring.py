"""Turn authored Markdown documents into a KnowledgeBundle (spec §5.2).

The bundle feeds the same import as the CLI, so chunking, enrichment and identity rules stay
in one place. Document keys are prefixed with the collection key: chunk ids derive from
section keys, and two collections must never share a point in Qdrant.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from pharma_agent.domain.corpus.bundle import (
    BUNDLE_SCHEMA_VERSION,
    BlockKind,
    BlockRecord,
    BundleCollection,
    BundleGenerator,
    BundleManifest,
    ColloquialMappingRecord,
    DocumentRecord,
    GlossaryEntry,
    KnowledgeBundle,
    SectionRecord,
    SourceInfo,
)
from pharma_agent.domain.corpus.models import Collection
from pharma_agent.domain.corpus.source import SourceDocument

AUTHORING_GENERATOR = BundleGenerator(
    name="vipharmind-authoring", version="1", build_id=""
)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, max_length: int = 80) -> str:
    """ASCII, lower case, words joined by hyphens; Vietnamese marks are dropped."""
    folded = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in folded if unicodedata.category(c) != "Mn").lower()
    return _NON_SLUG.sub("-", plain).strip("-")[:max_length].strip("-")


def document_key(collection: Collection, document: SourceDocument) -> str:
    return f"{collection.key}:{document.key}"


def section_key(document_key: str, path: Sequence[str]) -> str:
    if not path:
        return f"{document_key}#body"
    return f"{document_key}#{'/'.join(slugify(part) for part in path)}"


@dataclass(frozen=True)
class MarkdownSection:
    heading: str
    path: tuple[str, ...]
    ordinal: int
    blocks: list[BlockRecord]


def _blocks(lines: Sequence[str], next_table: list[int]) -> list[BlockRecord]:
    """Runs of table rows become table blocks; everything between them is prose."""
    blocks: list[BlockRecord] = []
    prose: list[str] = []
    table: list[str] = []
    in_fence = False

    def flush_prose() -> None:
        text = "\n".join(prose).strip()
        if text:
            blocks.append(BlockRecord(kind=BlockKind.PROSE, markdown=text))
        prose.clear()

    def flush_table() -> None:
        if table:
            next_table[0] += 1
            blocks.append(
                BlockRecord(
                    kind=BlockKind.TABLE,
                    markdown="\n".join(table).strip(),
                    table_key=f"t{next_table[0]}",
                )
            )
        table.clear()

    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.strip().startswith("|"):
            flush_prose()
            table.append(line.strip())
            continue
        flush_table()
        prose.append(line)
    flush_table()
    flush_prose()
    return blocks


def split_markdown(markdown: str, *, fallback_heading: str) -> list[MarkdownSection]:
    """Split on headings outside fenced code. Text before the first heading, or a
    document without headings, is a section titled `fallback_heading`. Sections without
    any content are dropped."""
    parts: list[tuple[str, tuple[str, ...], list[str]]] = [(fallback_heading, (), [])]
    stack: list[tuple[int, str]] = []
    in_fence = False
    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            parts[-1][2].append(line)
            continue
        level, heading = len(match.group(1)), match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        parts.append((heading, tuple(title for _, title in stack), []))
    sections: list[MarkdownSection] = []
    tables = [0]
    for heading, path, lines in parts:
        blocks = _blocks(lines, tables)
        if blocks:
            sections.append(MarkdownSection(heading, path, len(sections) + 1, blocks))
    return sections


def section_choices(
    collection: Collection, documents: Sequence[SourceDocument]
) -> list[tuple[str, str]]:
    """(section key, "Document › Heading") for every section, in reading order."""
    choices: list[tuple[str, str]] = []
    for document in documents:
        key = document_key(collection, document)
        for section in split_markdown(
            document.markdown, fallback_heading=document.title
        ):
            label = " › ".join([document.title, *section.path])
            choices.append((section_key(key, section.path), label))
    return choices


def build_bundle(
    collection: Collection,
    documents: Sequence[SourceDocument],
    glossary: Sequence[GlossaryEntry],
    colloquial: Sequence[ColloquialMappingRecord],
) -> KnowledgeBundle:
    """Deterministic: the same content gives the same bundle digest, so republishing
    unchanged content is a no-op."""
    document_records: list[DocumentRecord] = []
    section_records: list[SectionRecord] = []
    for document in sorted(documents, key=lambda d: d.key):
        key = document_key(collection, document)
        document_records.append(
            DocumentRecord(
                key=key,
                kind=document.kind,
                title=document.title,
                source=SourceInfo(
                    title=document.source_title or document.title,
                    url=document.source_url,
                ),
            )
        )
        for section in split_markdown(
            document.markdown, fallback_heading=document.title
        ):
            section_records.append(
                SectionRecord(
                    key=section_key(key, section.path),
                    document_key=key,
                    heading=section.heading,
                    context_path=list(section.path),
                    ordinal=section.ordinal,
                    blocks=section.blocks,
                )
            )
    known = {section.key for section in section_records}
    mappings = [
        mapping.model_copy(
            update={"section_keys": [k for k in mapping.section_keys if k in known]}
        )
        for mapping in colloquial
    ]
    return KnowledgeBundle(
        manifest=BundleManifest(
            schema_version=BUNDLE_SCHEMA_VERSION,
            collection=BundleCollection(key=collection.key, title=collection.title),
            generator=AUTHORING_GENERATOR,
            source_digests={},
            document_count=len(document_records),
            section_count=len(section_records),
            files={},
        ),
        documents=document_records,
        sections=section_records,
        glossary=list(glossary),
        colloquial_mappings=mappings,
    )
