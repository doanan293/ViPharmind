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
from pharma_agent.domain.corpus.models import collection_id_for, document_id_for


@dataclass(frozen=True)
class DocumentChunks:
    document: DocumentRecord
    sections: list[SectionRecord]
    drafts: list[ChunkDraft]


def gold_chunk_label(document_key: str, ordinal: int) -> str:
    """Position label used by evaluation gold sets: the document and the chunk's ordinal."""
    return f"{document_key}:chunk-{ordinal:03d}"


def iter_document_chunks(bundle: KnowledgeBundle) -> Iterator[DocumentChunks]:
    """Chunks of every document, packed as the bundle's manifest says, like the backend."""
    by_document: dict[str, list[SectionRecord]] = defaultdict(list)
    for section in bundle.sections:
        by_document[section.document_key].append(section)
    # The same ids the backend gives the documents of this bundle's collection.
    collection_id = collection_id_for(bundle.manifest.collection.key)
    for document in bundle.documents:
        sections = by_document.get(document.key, [])
        yield DocumentChunks(
            document=document,
            sections=sections,
            drafts=chunk_document(
                document_id_for(collection_id, document.key),
                document,
                sections,
                bundle.glossary,
                bundle.colloquial_mappings,
                target_chars=bundle.manifest.chunking.target_chars,
                max_chars=bundle.manifest.chunking.max_chars,
                enrichment=bundle.manifest.chunking.enrichment,
            ),
        )
