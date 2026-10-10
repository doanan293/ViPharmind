"""SessionStore over the fastapi-users `access_tokens` table."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.models import SessionRecord
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.tables import AccessTokenTable

# fastapi-users declares these columns with plain Python types for type checkers, so the
# SQL expressions below use the table's own columns.
_tokens = AccessTokenTable.__table__.c


class PostgresSessionStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        lifetime_seconds: int,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._lifetime = timedelta(seconds=lifetime_seconds)
        self._clock = clock

    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        oldest = self._clock.now() - self._lifetime
        statement = (
            select(AccessTokenTable)
            .where(
                _tokens.user_id == user_id,
                _tokens.created_at >= oldest,
            )
            .order_by(_tokens.created_at.desc())
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [
            SessionRecord(
                token=row.token,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                user_agent=row.user_agent,
                ip_address=row.ip_address,
            )
            for row in rows
        ]

    async def delete(self, user_id: uuid.UUID, token: str) -> bool:
        async with self._sessions.begin() as session:
            result = await session.execute(
                delete(AccessTokenTable)
                .where(_tokens.user_id == user_id, _tokens.token == token)
                .returning(_tokens.token)
            )
            return result.first() is not None

    async def delete_all(self, user_id: uuid.UUID, *, keep: str | None = None) -> int:
        statement = delete(AccessTokenTable).where(_tokens.user_id == user_id)
        if keep is not None:
            statement = statement.where(_tokens.token != keep)
        async with self._sessions.begin() as session:
            result = await session.execute(statement.returning(_tokens.token))
            return len(result.all())
