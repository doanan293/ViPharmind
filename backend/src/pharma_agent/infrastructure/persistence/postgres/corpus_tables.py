"""Tables of the Postgres schema `corpus` (spec 2026-09-13 corpus platform §6.2).

`section_revisions`, `chunk_versions` and `release_chunks` rows are
immutable once written; releases only change status. Chunk versions are protected by `RESTRICT` foreign keys so a citation can never
lose the text it points to.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pharma_agent.infrastructure.persistence.postgres.tables import Base

CORPUS_SCHEMA = "corpus"


def _created_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CollectionTable(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("key", name="uq_collections_key"),
        CheckConstraint(
            "visibility IN ('private', 'organization', 'public')", name="visibility"
        ),
        CheckConstraint(
            "owner_user_id IS NULL OR owner_organization_id IS NULL", name="one_owner"
        ),
        # A collection without an owner is the shared system corpus, always public.
        CheckConstraint(
            "owner_user_id IS NOT NULL OR owner_organization_id IS NOT NULL"
            " OR visibility = 'public'",
            name="system_is_public",
        ),
        CheckConstraint(
            "visibility <> 'organization' OR owner_organization_id IS NOT NULL",
            name="organization_needs_owner",
        ),
        Index("ix_collections_owner_user_id", "owner_user_id"),
        Index("ix_collections_owner_organization_id", "owner_organization_id"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=True
    )
    # No foreign key: deleting an organization marks its collections deleted instead,
    # because cited chunk versions are kept (RESTRICT) and block a cascade.
    owner_organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="private"
    )
    current_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "corpus.releases.id",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class DocumentTable(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("collection_id", "key", name="uq_documents_collection_key"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(Text, nullable=False)


class SectionTable(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("document_id", "key", name="uq_sections_document_key"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.documents.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(400), nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)


class SectionRevisionTable(Base):
    """A section's content-addressed revision id; chunk versions and citations join through it."""

    __tablename__ = "section_revisions"
    __table_args__ = ({"schema": CORPUS_SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.sections.id", ondelete="CASCADE"), nullable=False
    )


class ChunkVersionTable(Base):
    __tablename__ = "chunk_versions"
    __table_args__ = (
        Index("ix_chunk_versions_embedding_text_sha256", "embedding_text_sha256"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    section_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("corpus.section_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # From ChunkDraft.context_header, so readers (P3) never rebuild it.
    context_header: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    start_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    term_annotations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # none_as_null: Python None is stored as SQL NULL, not as the JSON value null.
    colloquial: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    chunker_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class ReleaseTable(Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "number", name="uq_releases_collection_number"
        ),
        CheckConstraint("status IN ('building', 'ready', 'retired')", name="status"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    bundle_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReleaseChunkTable(Base):
    __tablename__ = "release_chunks"
    __table_args__ = (
        Index(
            "ix_release_chunks_release_revision_ordinal",
            "release_id",
            "section_revision_id",
            "ordinal",
        ),
        Index("ix_release_chunks_chunk_version_id", "chunk_version_id"),
        {"schema": CORPUS_SCHEMA},
    )

    release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.releases.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("corpus.chunk_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.sections.id", ondelete="CASCADE"), nullable=False
    )
    section_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("corpus.section_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    hydrate_strategy: Mapped[str] = mapped_column(String(32), nullable=False)


class SourceDocumentTable(Base):
    """Documents written or uploaded in the app; the editable source of a bundle."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "key", name="uq_source_documents_collection_key"
        ),
        CheckConstraint(
            "kind IN ('drug_monograph', 'general_monograph', 'leaflet')", name="kind"
        ),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class GlossaryEntryTable(Base):
    __tablename__ = "glossary_entries"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "term", name="uq_glossary_entries_collection_term"
        ),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    vietnamese_expansions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    english_expansions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    category: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class ColloquialMappingTable(Base):
    __tablename__ = "colloquial_mappings"
    __table_args__ = (
        UniqueConstraint(
            "collection_id", "key", name="uq_colloquial_mappings_collection_key"
        ),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    visual_sign: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    product_names: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    section_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )


class IngestJobTable(Base):
    __tablename__ = "ingest_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed')", name="status"
        ),
        CheckConstraint(
            "step IN ('bundle', 'chunk', 'embed', 'index', 'publish')", name="step"
        ),
        Index(
            "uq_ingest_jobs_open",
            "collection_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_ingest_jobs_created", "created_at", "id"),
        {"schema": CORPUS_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("corpus.collections.id", ondelete="CASCADE"), nullable=False
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("corpus.releases.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    step: Mapped[str] = mapped_column(String(16), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
