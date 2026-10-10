"""Grant and revoke superadmin from the server, never from the web UI (spec §2)."""

from psycopg import AsyncConnection

_SET = 'UPDATE "user" SET is_superuser = %s WHERE lower(email) = lower(%s)'
_LIST = 'SELECT email FROM "user" WHERE is_superuser ORDER BY email'


async def set_superadmin(conninfo: str, email: str, value: bool) -> bool:
    """Set the flag on the account with `email`; False when no such account exists."""
    async with (
        await AsyncConnection.connect(conninfo) as connection,
        connection.transaction(),
    ):
        cursor = await connection.execute(_SET, (value, email.strip()))
    return cursor.rowcount == 1


async def list_superadmins(conninfo: str) -> list[str]:
    async with await AsyncConnection.connect(conninfo) as connection:
        cursor = await connection.execute(_LIST)
        return [row[0] for row in await cursor.fetchall()]
