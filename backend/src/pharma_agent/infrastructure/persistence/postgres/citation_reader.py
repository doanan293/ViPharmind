"""Stored citations read together with schema `corpus` (spec A §4.2, §5.2)."""

import uuid
from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.conversation.models import CitationBlock
from pharma_agent.infrastructure.persistence.postgres.citation_rows import (
    citation_from_row,
)
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    ChunkVersionTable,
    CollectionTable,
    DocumentTable,
)
from pharma_agent.infrastructure.persistence.postgres.tables import (
    ConversationTable,
    MessageCitationTable,
    MessageTable,
)


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(hex=value)
    except ValueError:
        return None


class PostgresCitationReader:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def current_release_ids(
        self, release_ids: Collection[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not release_ids:
            return set()
        query = select(CollectionTable.current_release_id).where(
            CollectionTable.current_release_id.in_(list(release_ids))
        )
        async with self._sessions() as session:
            found = (await session.execute(query)).scalars().all()
        return {release_id for release_id in found if release_id is not None}

    async def citation_block(
        self, user_id: str, message_id: str, index: int
    ) -> CitationBlock | None:
        owner, key = _uuid(user_id), _uuid(message_id)
        if owner is None or key is None:
            return None
        link_query = (
            select(MessageCitationTable)
            .join(MessageTable, MessageTable.id == MessageCitationTable.message_id)
            .join(
                ConversationTable, ConversationTable.id == MessageTable.conversation_id
            )
            .where(
                MessageCitationTable.message_id == key,
                MessageCitationTable.index == index,
                ConversationTable.user_id == owner,
            )
        )
        async with self._sessions() as session:
            link = (await session.execute(link_query)).scalar_one_or_none()
            if link is None:
                return None
            chunk_query = (
                select(
                    ChunkVersionTable,
                    DocumentTable.title,
                    DocumentTable.source_title,
                    CollectionTable.current_release_id,
                )
                .join(DocumentTable, DocumentTable.id == ChunkVersionTable.document_id)
                .join(
                    CollectionTable, CollectionTable.id == DocumentTable.collection_id
                )
                .where(ChunkVersionTable.id == link.chunk_version_id)
            )
            row = (await session.execute(chunk_query)).tuples().one()
        # FK RESTRICT keeps the cited chunk version and its document rows.
        chunk, document_title, source_title, current_release_id = row
        return CitationBlock(
            citation=citation_from_row(
                link, chunk, document_title=document_title, source_title=source_title
            ),
            text=chunk.chunk_text,
            is_current=current_release_id == link.release_id,
        )
