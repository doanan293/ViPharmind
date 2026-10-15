"""Postgres adapter of `CorpusRepository` over the schema `corpus`."""

import itertools
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.corpus.enrichment import compose_embedding_text
from pharma_agent.domain.corpus.models import (
    ChunkVersion,
    Collection,
    CorpusSnapshot,
    Document,
    IndexItem,
    PurgeResult,
    Release,
    ReleaseChunk,
    ReleaseNotFound,
    ReleaseStats,
    ReleaseStatus,
    ReleaseSummary,
    Section,
    Visibility,
)
from pharma_agent.domain.retrieval.models import ColloquialMapping, TermAnnotation
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    ChunkVersionTable,
    CollectionTable,
    DocumentTable,
    ReleaseChunkTable,
    ReleaseTable,
    SectionTable,
)
from pharma_agent.infrastructure.persistence.postgres.tables import Base

ROWS_PER_STATEMENT = 500


def _collection(row: CollectionTable) -> Collection:
    return Collection(
        id=row.id,
        key=row.key,
        title=row.title,
        owner_user_id=row.owner_user_id,
        visibility=Visibility(row.visibility),
        current_release_id=row.current_release_id,
    )


def _release(row: ReleaseTable) -> Release:
    return Release(
        id=row.id,
        collection_id=row.collection_id,
        number=row.number,
        status=ReleaseStatus(row.status),
        bundle_digest=row.bundle_digest,
        chunker_version=row.chunker_version,
        embedding_model=row.embedding_model,
        stats=ReleaseStats.model_validate(row.stats) if row.stats is not None else None,
        created_at=row.created_at,
        ready_at=row.ready_at,
        published_at=row.published_at,
        retired_at=row.retired_at,
    )


def _document_row(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "collection_id": document.collection_id,
        "key": document.key,
        "title": document.title,
        "source_title": document.source_title,
    }


def _section_row(section: Section) -> dict[str, Any]:
    return {
        "id": section.id,
        "document_id": section.document_id,
        "key": section.key,
        "heading": section.heading,
    }


def embedding_text_of(
    *,
    context_header: str,
    chunk_text: str,
    colloquial: dict[str, Any] | None,
    term_annotations: list[dict[str, Any]],
) -> str:
    """The text that was embedded, rebuilt from the stored columns (spec §4.9)."""
    return compose_embedding_text(
        context_header=context_header,
        chunk_text=chunk_text,
        colloquial=None
        if colloquial is None
        else ColloquialMapping.model_validate(colloquial),
        terms=[TermAnnotation.model_validate(item) for item in term_annotations],
    )


def _chunk_row(chunk: ChunkVersion) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "ordinal": chunk.ordinal,
        "section_keys": list(chunk.section_keys),
        "headings": list(chunk.headings),
        "chunk_text": chunk.chunk_text,
        "context_header": chunk.context_header,
        "embedding_text_sha256": chunk.embedding_text_sha256,
        "start_page": chunk.start_page,
        "end_page": chunk.end_page,
        "term_annotations": [
            annotation.model_dump(mode="json") for annotation in chunk.term_annotations
        ],
        "colloquial": chunk.colloquial.model_dump(mode="json")
        if chunk.colloquial is not None
        else None,
        "chunker_version": chunk.chunker_version,
    }


def _placement_row(release_id: uuid.UUID, placement: ReleaseChunk) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "chunk_version_id": placement.chunk_version_id,
        "document_id": placement.document_id,
        "ordinal": placement.ordinal,
    }


async def _insert(
    session: AsyncSession,
    table: type[Base],
    rows: Sequence[dict[str, Any]],
    *,
    conflict: Sequence[str],
    update_columns: Sequence[str] = (),
) -> None:
    for batch in itertools.batched(rows, ROWS_PER_STATEMENT):
        statement = insert(table).values(list(batch))
        if update_columns:
            statement = statement.on_conflict_do_update(
                index_elements=list(conflict),
                set_={name: statement.excluded[name] for name in update_columns},
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=list(conflict))
        await session.execute(statement)


async def _delete_unreferenced(
    session: AsyncSession,
    table: type[ChunkVersionTable],
    ids: Sequence[uuid.UUID],
) -> tuple[int, int]:
    """Delete rows, keeping those another table still references (FK RESTRICT).

    Each batch runs in a savepoint; a batch blocked by a foreign key is retried row by row so
    only the referenced rows survive. Returns (deleted, kept).
    """
    deleted = kept = 0
    for batch in itertools.batched(ids, ROWS_PER_STATEMENT):
        try:
            async with session.begin_nested():
                await session.execute(delete(table).where(table.id.in_(batch)))
            deleted += len(batch)
        except IntegrityError:
            for row_id in batch:
                try:
                    async with session.begin_nested():
                        await session.execute(delete(table).where(table.id == row_id))
                    deleted += 1
                except IntegrityError:
                    kept += 1
    return deleted, kept


class PostgresCorpusRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_collection(self, key: str) -> Collection | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(CollectionTable).where(CollectionTable.key == key)
                )
            ).scalar_one_or_none()
        return _collection(row) if row is not None else None

    async def get_release(self, release_id: uuid.UUID) -> Release | None:
        async with self._sessions() as session:
            row = await session.get(ReleaseTable, release_id)
        return _release(row) if row is not None else None

    async def find_release(
        self,
        collection_id: uuid.UUID,
        *,
        bundle_digest: str,
        chunker_version: str,
        embedding_model: str,
    ) -> Release | None:
        query = (
            select(ReleaseTable)
            .where(
                ReleaseTable.collection_id == collection_id,
                ReleaseTable.bundle_digest == bundle_digest,
                ReleaseTable.chunker_version == chunker_version,
                ReleaseTable.embedding_model == embedding_model,
                ReleaseTable.status != ReleaseStatus.RETIRED.value,
            )
            .order_by(ReleaseTable.number.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(query)).scalar_one_or_none()
        return _release(row) if row is not None else None

    async def list_releases(self, collection_key: str | None) -> list[ReleaseSummary]:
        chunk_counts = (
            select(
                ReleaseChunkTable.release_id,
                func.count().label("chunks"),
            )
            .group_by(ReleaseChunkTable.release_id)
            .subquery()
        )
        query = (
            select(
                ReleaseTable,
                CollectionTable.key,
                CollectionTable.current_release_id,
                func.coalesce(chunk_counts.c.chunks, 0),
            )
            .join(CollectionTable, CollectionTable.id == ReleaseTable.collection_id)
            .outerjoin(chunk_counts, chunk_counts.c.release_id == ReleaseTable.id)
            .order_by(CollectionTable.key, ReleaseTable.number.desc())
        )
        if collection_key is not None:
            query = query.where(CollectionTable.key == collection_key)
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return [
            ReleaseSummary(
                collection_key=key,
                release=_release(release),
                chunk_count=int(chunks),
                current=current_release_id == release.id,
            )
            for release, key, current_release_id, chunks in rows
        ]

    async def stage_release(
        self,
        snapshot: CorpusSnapshot,
        *,
        release_id: uuid.UUID,
        embedding_model: str,
        at: datetime,
    ) -> Release:
        collection = snapshot.collection
        async with self._sessions.begin() as session:
            statement = insert(CollectionTable).values(
                id=collection.id,
                key=collection.key,
                title=collection.title,
                owner_user_id=collection.owner_user_id,
                visibility=collection.visibility.value,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["key"],
                    set_={"title": statement.excluded.title, "updated_at": func.now()},
                )
            )
            await _insert(
                session,
                DocumentTable,
                [_document_row(document) for document in snapshot.documents],
                conflict=["collection_id", "key"],
                update_columns=["title", "source_title"],
            )
            await _insert(
                session,
                SectionTable,
                [_section_row(section) for section in snapshot.sections],
                conflict=["document_id", "key"],
                update_columns=["heading"],
            )
            await _insert(
                session,
                ChunkVersionTable,
                [_chunk_row(chunk) for chunk in snapshot.chunks],
                conflict=["id"],
            )
            row = await session.get(ReleaseTable, release_id)
            if row is None:
                last = (
                    await session.execute(
                        select(func.coalesce(func.max(ReleaseTable.number), 0)).where(
                            ReleaseTable.collection_id == collection.id
                        )
                    )
                ).scalar_one()
                row = ReleaseTable(
                    id=release_id,
                    collection_id=collection.id,
                    number=last + 1,
                    status=ReleaseStatus.BUILDING.value,
                    bundle_digest=snapshot.bundle_digest,
                    chunker_version=snapshot.chunker_version,
                    embedding_model=embedding_model,
                    created_at=at,
                )
                session.add(row)
                await session.flush()
                await _insert(
                    session,
                    ReleaseChunkTable,
                    [
                        _placement_row(release_id, placement)
                        for placement in snapshot.release_chunks
                    ],
                    conflict=["release_id", "chunk_version_id"],
                )
            return _release(row)

    async def index_items(self, release_ids: Sequence[uuid.UUID]) -> list[IndexItem]:
        if not release_ids:
            return []
        chunk_ids = select(ReleaseChunkTable.chunk_version_id).where(
            ReleaseChunkTable.release_id.in_(list(release_ids))
        )
        items_query = (
            select(
                ChunkVersionTable.id,
                DocumentTable.collection_id,
                ChunkVersionTable.document_id,
                ChunkVersionTable.context_header,
                ChunkVersionTable.chunk_text,
                ChunkVersionTable.colloquial,
                ChunkVersionTable.term_annotations,
                ChunkVersionTable.embedding_text_sha256,
            )
            .join(DocumentTable, DocumentTable.id == ChunkVersionTable.document_id)
            .where(ChunkVersionTable.id.in_(chunk_ids))
            .order_by(ChunkVersionTable.id)
        )
        memberships_query = (
            select(
                ReleaseChunkTable.chunk_version_id,
                func.array_agg(ReleaseChunkTable.release_id),
            )
            .join(ReleaseTable, ReleaseTable.id == ReleaseChunkTable.release_id)
            .where(
                ReleaseTable.status != ReleaseStatus.RETIRED.value,
                ReleaseChunkTable.chunk_version_id.in_(chunk_ids),
            )
            .group_by(ReleaseChunkTable.chunk_version_id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(items_query)).all()
            memberships: dict[uuid.UUID, list[uuid.UUID]] = {
                chunk_id: sorted(releases)
                for chunk_id, releases in (
                    await session.execute(memberships_query)
                ).all()
            }
        return [
            IndexItem(
                chunk_version_id=chunk_id,
                collection_id=collection_id,
                document_id=document_id,
                embedding_text=embedding_text_of(
                    context_header=context_header,
                    chunk_text=chunk_text,
                    colloquial=colloquial,
                    term_annotations=term_annotations,
                ),
                embedding_text_sha256=embedding_text_sha256,
                release_ids=memberships.get(chunk_id, []),
            )
            for (
                chunk_id,
                collection_id,
                document_id,
                context_header,
                chunk_text,
                colloquial,
                term_annotations,
                embedding_text_sha256,
            ) in rows
        ]

    async def mark_ready(
        self, release_id: uuid.UUID, stats: ReleaseStats, at: datetime
    ) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ReleaseTable)
                .where(ReleaseTable.id == release_id)
                .values(
                    status=ReleaseStatus.READY.value,
                    stats=stats.model_dump(mode="json"),
                    ready_at=at,
                )
            )

    async def publish(self, release_id: uuid.UUID, at: datetime) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(ReleaseTable, release_id)
            if row is None:
                raise ReleaseNotFound(str(release_id))
            await session.execute(
                update(CollectionTable)
                .where(CollectionTable.id == row.collection_id)
                .values(current_release_id=release_id, updated_at=func.now())
            )
            await session.execute(
                update(ReleaseTable)
                .where(ReleaseTable.id == release_id)
                .values(published_at=func.coalesce(ReleaseTable.published_at, at))
            )

    async def retire(self, release_ids: Sequence[uuid.UUID], at: datetime) -> None:
        if not release_ids:
            return
        async with self._sessions.begin() as session:
            await session.execute(
                update(ReleaseTable)
                .where(
                    ReleaseTable.id.in_(list(release_ids)),
                    ReleaseTable.status != ReleaseStatus.RETIRED.value,
                )
                .values(status=ReleaseStatus.RETIRED.value, retired_at=at)
            )

    async def purge_retired(self, collection_id: uuid.UUID) -> PurgeResult:
        retired = select(ReleaseTable.id).where(
            ReleaseTable.collection_id == collection_id,
            ReleaseTable.status == ReleaseStatus.RETIRED.value,
        )
        collection_documents = select(DocumentTable.id).where(
            DocumentTable.collection_id == collection_id
        )
        async with self._sessions.begin() as session:
            placements = (
                await session.execute(
                    delete(ReleaseChunkTable)
                    .where(ReleaseChunkTable.release_id.in_(retired))
                    .returning(ReleaseChunkTable.chunk_version_id)
                )
            ).all()
            orphan_chunks = (
                (
                    await session.execute(
                        select(ChunkVersionTable.id)
                        .where(
                            ChunkVersionTable.document_id.in_(collection_documents),
                            ~exists().where(
                                ReleaseChunkTable.chunk_version_id
                                == ChunkVersionTable.id
                            ),
                        )
                        .order_by(ChunkVersionTable.id)
                    )
                )
                .scalars()
                .all()
            )
            chunks_deleted, chunks_kept = await _delete_unreferenced(
                session, ChunkVersionTable, orphan_chunks
            )
            live_documents = select(ChunkVersionTable.document_id).union(
                select(ReleaseChunkTable.document_id)
            )
            sections_deleted = len(
                (
                    await session.execute(
                        delete(SectionTable)
                        .where(
                            SectionTable.document_id.in_(collection_documents),
                            SectionTable.document_id.not_in(live_documents),
                        )
                        .returning(SectionTable.id)
                    )
                ).all()
            )
            documents_deleted = len(
                (
                    await session.execute(
                        delete(DocumentTable)
                        .where(
                            DocumentTable.collection_id == collection_id,
                            DocumentTable.id.not_in(live_documents),
                        )
                        .returning(DocumentTable.id)
                    )
                ).all()
            )
        return PurgeResult(
            release_chunks_deleted=len(placements),
            chunk_versions_deleted=chunks_deleted,
            chunk_versions_kept=chunks_kept,
            sections_deleted=sections_deleted,
            documents_deleted=documents_deleted,
        )
