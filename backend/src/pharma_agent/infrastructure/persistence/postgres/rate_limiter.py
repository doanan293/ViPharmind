"""RateLimiter over `rate_limit_buckets`: one row per key, its window opened by the first action."""

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.tables import RateLimitBucketTable

_bucket = RateLimitBucketTable.__table__.c


def _expired(now: datetime, window_seconds: int) -> ColumnElement[bool]:
    return _bucket.window_start <= now - timedelta(seconds=window_seconds)


def _count_one(
    key: str, now: datetime, window_seconds: int, *, limit: int | None
) -> ReturningInsert[tuple[datetime, int]]:
    """Count one action for `key`; a closed window restarts at `now`.

    With `limit`, an open window already at the limit is left alone and no row comes
    back. The row lock taken by ON CONFLICT makes the check and the count one step.
    """
    expired = _expired(now, window_seconds)
    statement = insert(RateLimitBucketTable).values(key=key, window_start=now, count=1)
    return statement.on_conflict_do_update(
        index_elements=[_bucket.key],
        set_={
            "window_start": case((expired, now), else_=_bucket.window_start),
            "count": case((expired, 1), else_=_bucket.count + 1),
        },
        where=None if limit is None else expired | (_bucket.count < limit),
    ).returning(_bucket.window_start, _bucket.count)


def _wait(window_start: datetime, now: datetime, window_seconds: int) -> float:
    end = window_start + timedelta(seconds=window_seconds)
    # A refusal always asks for some wait, even as the window is closing.
    return max((end - now).total_seconds(), 1.0)


class PostgresRateLimiter:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    async def _open_window(
        self, session: AsyncSession, key: str, now: datetime, window_seconds: int
    ) -> tuple[datetime, int] | None:
        row = (
            await session.execute(
                select(_bucket.window_start, _bucket.count).where(
                    _bucket.key == key, ~_expired(now, window_seconds)
                )
            )
        ).one_or_none()
        if row is None:
            return None
        window_start, count = row
        return window_start, count

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        now = self._clock.now()
        async with self._sessions() as session:
            window = await self._open_window(session, key, now, window_seconds)
        if window is None or window[1] < limit:
            return None
        return _wait(window[0], now, window_seconds)

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        now = self._clock.now()
        async with self._sessions.begin() as session:
            result = await session.execute(
                _count_one(key, now, window_seconds, limit=None)
            )
            window_start, count = result.one()
        if count > limit:
            return _wait(window_start, now, window_seconds)
        return None

    async def acquire(
        self, key: str, *, limit: int, window_seconds: int
    ) -> float | None:
        now = self._clock.now()
        async with self._sessions.begin() as session:
            counted = (
                await session.execute(_count_one(key, now, window_seconds, limit=limit))
            ).one_or_none()
            if counted is not None:
                return None
            window = await self._open_window(session, key, now, window_seconds)
        return (
            float(window_seconds)
            if window is None
            else _wait(window[0], now, window_seconds)
        )

    async def release(self, key: str, *, window_seconds: int) -> None:
        now = self._clock.now()
        async with self._sessions.begin() as session:
            await session.execute(
                update(RateLimitBucketTable)
                .where(_bucket.key == key, ~_expired(now, window_seconds))
                .values(count=func.greatest(_bucket.count - 1, 0))
            )
