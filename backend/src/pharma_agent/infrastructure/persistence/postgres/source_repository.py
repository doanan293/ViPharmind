"""SourceRepository over the authored-content tables of schema `corpus`."""

import uuid

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.corpus.bundle import (
    ColloquialMappingRecord,
    DocumentKind,
    GlossaryEntry,
)
from pharma_agent.domain.corpus.models import CollectionOwner
from pharma_agent.domain.corpus.source import DocumentKeyConflict, SourceDocument
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    CollectionTable,
    ColloquialMappingTable,
    GlossaryEntryTable,
    SourceDocumentTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_doc = SourceDocumentTable.__table__.c
_gloss = GlossaryEntryTable.__table__.c
_coll = ColloquialMappingTable.__table__.c
_c = CollectionTable.__table__.c


def _document(row: SourceDocumentTable) -> SourceDocument:
    return SourceDocument(
        id=row.id,
        collection_id=row.collection_id,
        key=row.key,
        title=row.title,
        kind=DocumentKind(row.kind),
        source_title=row.source_title,
        source_url=row.source_url,
        markdown=row.markdown,
        char_count=row.char_count,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


def _values(document: SourceDocument) -> dict[str, object]:
    return {
        "title": document.title,
        "kind": document.kind.value,
        "source_title": document.source_title,
        "source_url": document.source_url,
        "markdown": document.markdown,
        "char_count": document.char_count,
        "updated_by": document.updated_by,
        "updated_at": document.updated_at,
    }


class PostgresSourceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_documents(self, collection_id: uuid.UUID) -> list[SourceDocument]:
        query = (
            select(SourceDocumentTable)
            .where(_doc.collection_id == collection_id)
            .order_by(_doc.title, _doc.id)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [_document(row) for row in rows]

    async def get_document(self, document_id: uuid.UUID) -> SourceDocument | None:
        async with self._sessions() as session:
            row = await session.get(SourceDocumentTable, document_id)
        return None if row is None else _document(row)

    async def document_keys(self, collection_id: uuid.UUID) -> set[str]:
        query = select(_doc.key).where(_doc.collection_id == collection_id)
        async with self._sessions() as session:
            return set((await session.scalars(query)).all())

    async def create_document(self, document: SourceDocument, tx: Transaction) -> None:
        session = session_of(tx)
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(SourceDocumentTable).values(
                        id=document.id,
                        collection_id=document.collection_id,
                        key=document.key,
                        created_by=document.created_by,
                        created_at=document.created_at,
                        **_values(document),
                    )
                )
        except IntegrityError as exc:
            raise DocumentKeyConflict(f"the key {document.key} is taken") from exc

    async def update_document(self, document: SourceDocument, tx: Transaction) -> None:
        await session_of(tx).execute(
            update(SourceDocumentTable)
            .where(_doc.id == document.id)
            .values(**_values(document))
        )

    async def delete_document(self, document_id: uuid.UUID, tx: Transaction) -> None:
        await session_of(tx).execute(
            delete(SourceDocumentTable).where(_doc.id == document_id)
        )

    async def purge_content(self, collection_id: uuid.UUID, tx: Transaction) -> None:
        session = session_of(tx)
        await session.execute(
            delete(SourceDocumentTable).where(_doc.collection_id == collection_id)
        )
        await session.execute(
            delete(GlossaryEntryTable).where(_gloss.collection_id == collection_id)
        )
        await session.execute(
            delete(ColloquialMappingTable).where(_coll.collection_id == collection_id)
        )

    async def count_documents(self, collection_id: uuid.UUID) -> int:
        query = select(func.count()).where(_doc.collection_id == collection_id)
        async with self._sessions() as session:
            return (await session.execute(query)).scalar_one()

    async def text_usage(self, owner: CollectionOwner) -> int:
        query = (
            select(func.coalesce(func.sum(_doc.char_count), 0))
            .join(CollectionTable, _c.id == _doc.collection_id)
            .where(
                _c.deleted_at.is_(None),
                _c.owner_user_id.is_(None)
                if owner.user_id is None
                else _c.owner_user_id == owner.user_id,
                _c.owner_organization_id.is_(None)
                if owner.organization_id is None
                else _c.owner_organization_id == owner.organization_id,
            )
        )
        async with self._sessions() as session:
            return int((await session.execute(query)).scalar_one())

    async def glossary(self, collection_id: uuid.UUID) -> list[GlossaryEntry]:
        query = (
            select(GlossaryEntryTable)
            .where(_gloss.collection_id == collection_id)
            .order_by(_gloss.position)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [
            GlossaryEntry(
                term=row.term,
                case_sensitive=row.case_sensitive,
                vietnamese_expansions=list(row.vietnamese_expansions),
                english_expansions=list(row.english_expansions),
                aliases=list(row.aliases),
                category=row.category,
            )
            for row in rows
        ]

    async def replace_glossary(
        self,
        collection_id: uuid.UUID,
        entries: list[GlossaryEntry],
        tx: Transaction,
    ) -> None:
        session = session_of(tx)
        await session.execute(
            delete(GlossaryEntryTable).where(_gloss.collection_id == collection_id)
        )
        if entries:
            await session.execute(
                insert(GlossaryEntryTable),
                [
                    {
                        "id": uuid.uuid4(),
                        "collection_id": collection_id,
                        "position": position,
                        "term": entry.term.strip(),
                        "case_sensitive": entry.case_sensitive,
                        "vietnamese_expansions": entry.vietnamese_expansions,
                        "english_expansions": entry.english_expansions,
                        "aliases": entry.aliases,
                        "category": entry.category,
                    }
                    for position, entry in enumerate(entries)
                ],
            )

    async def colloquial(
        self, collection_id: uuid.UUID
    ) -> list[ColloquialMappingRecord]:
        query = (
            select(ColloquialMappingTable)
            .where(_coll.collection_id == collection_id)
            .order_by(_coll.position)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [
            ColloquialMappingRecord(
                key=row.key,
                aliases=list(row.aliases),
                visual_sign=row.visual_sign,
                product_names=list(row.product_names),
                section_keys=list(row.section_keys),
            )
            for row in rows
        ]

    async def replace_colloquial(
        self,
        collection_id: uuid.UUID,
        mappings: list[ColloquialMappingRecord],
        tx: Transaction,
    ) -> None:
        session = session_of(tx)
        await session.execute(
            delete(ColloquialMappingTable).where(_coll.collection_id == collection_id)
        )
        if mappings:
            await session.execute(
                insert(ColloquialMappingTable),
                [
                    {
                        "id": uuid.uuid4(),
                        "collection_id": collection_id,
                        "position": position,
                        "key": mapping.key.strip(),
                        "aliases": mapping.aliases,
                        "visual_sign": mapping.visual_sign,
                        "product_names": mapping.product_names,
                        "section_keys": mapping.section_keys,
                    }
                    for position, mapping in enumerate(mappings)
                ],
            )
