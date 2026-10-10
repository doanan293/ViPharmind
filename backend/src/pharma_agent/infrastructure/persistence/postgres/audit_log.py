"""AuditLog over `audit_events`, newest first with keyset pages."""

import uuid
from typing import Any

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Uuid,
    insert,
    literal,
    select,
    true,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.audit.models import AuditAction, AuditEvent
from pharma_agent.domain.audit.ports import Cursor
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.tables import AuditEventTable
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_event = AuditEventTable.__table__.c


def _event_of(row: AuditEventTable) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        occurred_at=row.occurred_at,
        actor_user_id=row.actor_user_id,
        actor_was_superadmin=row.actor_was_superadmin,
        action=AuditAction(row.action),
        organization_id=row.organization_id,
        subject_user_id=row.subject_user_id,
        collection_id=row.collection_id,
        details=row.details,
    )


class PostgresAuditLog:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, event: AuditEvent, tx: Transaction) -> None:
        details: dict[str, Any] = dict(event.details)
        await session_of(tx).execute(
            insert(AuditEventTable).values(
                id=event.id,
                occurred_at=event.occurred_at,
                actor_user_id=event.actor_user_id,
                actor_was_superadmin=event.actor_was_superadmin,
                action=event.action.value,
                organization_id=event.organization_id,
                subject_user_id=event.subject_user_id,
                collection_id=event.collection_id,
                details=details,
            )
        )

    async def _page(
        self, condition: ColumnElement[bool], limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        query = select(AuditEventTable).where(condition)
        if cursor is not None:
            at, key = cursor
            query = query.where(
                tuple_(_event.occurred_at, _event.id)
                < tuple_(
                    literal(at, DateTime(timezone=True)),
                    literal(uuid.UUID(hex=key), Uuid()),
                )
            )
        query = query.order_by(_event.occurred_at.desc(), _event.id.desc()).limit(limit)
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [_event_of(row) for row in rows]

    async def for_organization(
        self, organization_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        return await self._page(
            _event.organization_id == organization_id, limit, cursor
        )

    async def for_user(
        self, user_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        return await self._page(_event.subject_user_id == user_id, limit, cursor)

    async def all(self, *, limit: int, cursor: Cursor | None) -> list[AuditEvent]:
        return await self._page(true(), limit, cursor)
