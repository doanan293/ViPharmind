"""Retention for cookie sessions: fastapi-users ignores expired access tokens but never deletes them."""

from psycopg import AsyncConnection

_DELETE_EXPIRED = """
DELETE FROM access_tokens
WHERE created_at < now() - make_interval(secs => %s)
"""


async def delete_expired_access_tokens(conninfo: str, *, lifetime_seconds: int) -> int:
    """Delete access tokens older than `lifetime_seconds` and return how many were removed.

    `DatabaseStrategy` treats exactly these rows as expired (`created_at` before now minus
    the lifetime), so deleting them never logs out a valid session.
    """
    async with (
        await AsyncConnection.connect(conninfo) as connection,
        connection.transaction(),
    ):
        cursor = await connection.execute(_DELETE_EXPIRED, (lifetime_seconds,))
    return cursor.rowcount


_DELETE_STALE_CODES = (
    "DELETE FROM one_time_codes WHERE expires_at < now() - interval '1 day'"
)
_DELETE_STALE_BUCKETS = (
    "DELETE FROM rate_limit_buckets WHERE window_start < now() - interval '1 day'"
)


async def delete_stale_account_rows(conninfo: str) -> tuple[int, int]:
    """Delete codes expired over a day ago and rate-limit windows older than a day.

    The longest window is one hour, so a day-old bucket never limits anything.
    """
    async with (
        await AsyncConnection.connect(conninfo) as connection,
        connection.transaction(),
    ):
        codes = await connection.execute(_DELETE_STALE_CODES)
        buckets = await connection.execute(_DELETE_STALE_BUCKETS)
    return codes.rowcount, buckets.rowcount
