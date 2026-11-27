from collections.abc import Mapping
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

type ReleaseScope = Mapping[UUID, UUID]
"""collection_id -> its current release_id: exactly what one search may read. Empty means
there is nothing the user may search."""


class QueryOrigin(StrEnum):
    """Where a query came from: the user's turn or a refinement."""

    INITIAL = "initial"
    REFINED = "refined"


class Query(BaseModel):
    """A search query and its origin."""

    model_config = ConfigDict(frozen=True)

    text: str
    origin: QueryOrigin

    @property
    def normalized(self) -> str:
        """Lowercased with whitespace collapsed, for duplicate checks."""
        return " ".join(self.text.lower().split())


class TermAnnotation(BaseModel):
    """Expansions of a glossary term found in a chunk, in Vietnamese and English."""

    term: str
    vi: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)


class ColloquialMapping(BaseModel):
    """Colloquial names attached to a chunk's sections."""

    key: str = ""
    aliases: list[str] = Field(default_factory=list)
    visual_sign: str = ""
    product_names: list[str] = Field(default_factory=list)


def page_label(start_page: int | None, end_page: int | None) -> str:
    """Vietnamese page label; empty when the source has no page numbers (leaflets)."""
    if start_page is None and end_page is None:
        return ""
    if start_page is None or end_page is None or start_page == end_page:
        return f"trang {start_page if start_page is not None else end_page}"
    return f"trang {start_page}-{end_page}"


class Hit(BaseModel):
    """One chunk version found by search, as published in one release, plus scores."""

    chunk_version_id: UUID
    release_id: UUID
    collection_id: UUID
    document_key: str
    ordinal: int
    section_keys: list[str]
    headings: list[str]
    source: str
    title: str
    start_page: int | None
    end_page: int | None
    context_header: str
    chunk_text: str
    # What was embedded and what the reranker scores, unchanged from today.
    embedding_text: str
    colloquial_mapping: ColloquialMapping | None = None
    term_annotations: list[TermAnnotation] = Field(default_factory=list)
    fusion_score: float = 0.0
    rerank_score: float | None = None
    matched_queries: list[str] = Field(default_factory=list)

    @property
    def score(self) -> float:
        """The rerank score, or the fusion score when the hit was not reranked."""
        return self.rerank_score if self.rerank_score is not None else self.fusion_score

    @property
    def section(self) -> str:
        """The headings of the sections this chunk holds, in reading order."""
        return "; ".join(h for h in self.headings if h)

    @property
    def page_label(self) -> str:
        """Vietnamese page label of the chunk; empty without page numbers."""
        return page_label(self.start_page, self.end_page)

    def term_hints(self) -> list[str]:
        """Colloquial names and glossary expansions, de-duplicated ignoring case."""
        hints: list[str] = []
        if self.colloquial_mapping is not None:
            hints.extend(self.colloquial_mapping.aliases)
            hints.extend(self.colloquial_mapping.product_names)
        for annotation in self.term_annotations:
            hints.append(annotation.term)
            hints.extend(annotation.vi)
            hints.extend(annotation.en)
        seen: set[str] = set()
        unique: list[str] = []
        for hint in hints:
            key = hint.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(hint.strip())
        return unique


class ChunkRecord(BaseModel):
    """One chunk version as published in one release, with the fields a search hit shows."""

    model_config = ConfigDict(frozen=True)

    chunk_version_id: UUID
    release_id: UUID
    collection_id: UUID
    document_key: str
    ordinal: int
    section_keys: list[str]
    headings: list[str]
    source: str
    title: str
    start_page: int | None
    end_page: int | None
    context_header: str
    chunk_text: str
    embedding_text: str
    colloquial_mapping: ColloquialMapping | None = None
    term_annotations: list[TermAnnotation] = Field(default_factory=list)

    @property
    def section(self) -> str:
        """The headings of the sections this chunk holds, in reading order."""
        return "; ".join(h for h in self.headings if h)

    def to_hit(self, *, fusion_score: float, query_text: str) -> Hit:
        """A search hit of this chunk matched by `query_text`, not yet reranked."""
        return Hit.model_validate(
            {
                **self.model_dump(),
                "fusion_score": fusion_score,
                "matched_queries": [query_text],
            }
        )
