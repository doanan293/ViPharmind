"""Fixed-window RateLimiter over `rate_limit_buckets`."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.tables import RateLimitBucketTable


class PostgresRateLimiter:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    def _window(self, window_seconds: int) -> tuple[datetime, float]:
        """The current window's start and the seconds left in it."""
        epoch = self._clock.now().timestamp()
        start = epoch - epoch % window_seconds
        return datetime.fromtimestamp(start, UTC), start + window_seconds - epoch

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._window(window_seconds)
        async with self._sessions() as session:
            count = (
                await session.execute(
                    select(RateLimitBucketTable.count).where(
                        RateLimitBucketTable.key == key,
                        RateLimitBucketTable.window_start == start,
                    )
                )
            ).scalar_one_or_none()
        return remaining if (count or 0) >= limit else None

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._window(window_seconds)
        statement = (
            insert(RateLimitBucketTable)
            .values(key=key, window_start=start, count=1)
            .on_conflict_do_update(
                index_elements=["key", "window_start"],
                set_={"count": RateLimitBucketTable.count + 1},
            )
            .returning(RateLimitBucketTable.count)
        )
        async with self._sessions.begin() as session:
            count = (await session.execute(statement)).scalar_one()
        return remaining if count > limit else None
