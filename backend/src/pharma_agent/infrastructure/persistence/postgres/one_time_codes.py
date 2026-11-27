"""OneTimeCodeStore over `one_time_codes`."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import (
    CHANNEL_BY_PURPOSE,
    OneTimeCode,
    OtpPurpose,
)
from pharma_agent.infrastructure.persistence.postgres.tables import OneTimeCodeTable


class PostgresOneTimeCodeStore:
    """OneTimeCodeStore over `one_time_codes`; each method runs in its own transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Store codes through sessions from `sessions`."""
        self._sessions = sessions

    async def issue(
        self,
        *,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> uuid.UUID:
        """Store a code and drop every unused code for the same purpose and destination."""
        code_id = uuid.uuid4()
        async with self._sessions.begin() as session:
            await session.execute(
                delete(OneTimeCodeTable).where(
                    OneTimeCodeTable.purpose == purpose.value,
                    OneTimeCodeTable.destination == destination,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
            )
            session.add(
                OneTimeCodeTable(
                    id=code_id,
                    purpose=purpose.value,
                    channel=CHANNEL_BY_PURPOSE[purpose].value,
                    destination=destination,
                    user_id=user_id,
                    code_hash=digest,
                    expires_at=expires_at,
                    attempts=0,
                    created_at=now,
                )
            )
        return code_id

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        """The newest unused, unexpired code with fewer than MAX_ATTEMPTS failures."""
        statement = (
            select(OneTimeCodeTable)
            .where(
                OneTimeCodeTable.purpose == purpose.value,
                OneTimeCodeTable.destination == destination,
                OneTimeCodeTable.consumed_at.is_(None),
                OneTimeCodeTable.expires_at > now,
                OneTimeCodeTable.attempts < MAX_ATTEMPTS,
            )
            .order_by(OneTimeCodeTable.created_at.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        return OneTimeCode(
            id=row.id,
            purpose=OtpPurpose(row.purpose),
            destination=row.destination,
            user_id=row.user_id,
            digest=row.code_hash,
            expires_at=row.expires_at,
            attempts=row.attempts,
        )

    async def claim_attempt(self, code_id: uuid.UUID) -> bool:
        """Count one guess before it is compared; False once MAX_ATTEMPTS were claimed.

        A single conditional UPDATE, so parallel guesses cannot exceed the limit.
        """
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(OneTimeCodeTable)
                .where(
                    OneTimeCodeTable.id == code_id,
                    OneTimeCodeTable.consumed_at.is_(None),
                    OneTimeCodeTable.attempts < MAX_ATTEMPTS,
                )
                .values(attempts=OneTimeCodeTable.attempts + 1)
                .returning(OneTimeCodeTable.id)
            )
            return result.first() is not None

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        """Mark the code used; False if it was already used (exactly one caller wins)."""
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(OneTimeCodeTable)
                .where(
                    OneTimeCodeTable.id == code_id,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
                .values(consumed_at=now)
                .returning(OneTimeCodeTable.id)
            )
            return result.first() is not None

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None:
        """Mark the code used if it is not already."""
        async with self._sessions.begin() as session:
            await session.execute(
                update(OneTimeCodeTable)
                .where(
                    OneTimeCodeTable.id == code_id,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
