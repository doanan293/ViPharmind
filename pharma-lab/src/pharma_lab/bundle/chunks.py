"""Run the backend chunker over every document of a knowledge bundle."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from pharma_agent.domain.corpus.bundle import (
    DocumentRecord,
    KnowledgeBundle,
    SectionRecord,
)
from pharma_agent.domain.corpus.chunking import ChunkDraft, chunk_document


@dataclass(frozen=True)
class DocumentChunks:
    document: DocumentRecord
    sections: list[SectionRecord]
    drafts: list[ChunkDraft]


def gold_chunk_label(document_key: str, ordinal: int) -> str:
    """Position label used by evaluation gold sets: the document and the chunk's ordinal."""
    return f"{document_key}:chunk-{ordinal:03d}"


def iter_document_chunks(bundle: KnowledgeBundle) -> Iterator[DocumentChunks]:
    by_document: dict[str, list[SectionRecord]] = defaultdict(list)
    for section in bundle.sections:
        by_document[section.document_key].append(section)
    for document in bundle.documents:
        sections = by_document.get(document.key, [])
        yield DocumentChunks(
            document=document,
            sections=sections,
            drafts=chunk_document(
                document, sections, bundle.glossary, bundle.colloquial_mappings
            ),
        )
