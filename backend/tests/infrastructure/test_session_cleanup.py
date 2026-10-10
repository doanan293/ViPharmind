import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from pharma_agent.infrastructure.auth.session_cleanup import (
    delete_expired_access_tokens,
    delete_stale_account_rows,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.tables import (
    AccessTokenTable,
    UserTable,
)

pytestmark = pytest.mark.integration

LIFETIME = 7 * 24 * 3600


@pytest.fixture
async def database(migrated_dsn: str) -> AsyncGenerator[Database]:
    db = Database(migrated_dsn, pool_size=2)
    async with db.engine.begin() as connection:
        await connection.execute(text("TRUNCATE access_tokens"))
    yield db
    await db.dispose()


async def test_only_expired_sessions_are_deleted(
    database: Database, migrated_dsn: str
) -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with database.sessions.begin() as session:
        session.add(
            UserTable(
                id=user_id,
                email=f"{user_id.hex[:12]}@example.com",
                hashed_password="x",
            )
        )
        await session.flush()
        session.add_all(
            [
                AccessTokenTable(
                    token="expired-token",
                    user_id=user_id,
                    created_at=now - timedelta(seconds=LIFETIME + 60),
                ),
                AccessTokenTable(
                    token="fresh-token",
                    user_id=user_id,
                    created_at=now - timedelta(seconds=LIFETIME - 60),
                ),
            ]
        )
    conninfo = (
        make_url(migrated_dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )

    assert await delete_expired_access_tokens(conninfo, lifetime_seconds=LIFETIME) == 1

    async with database.sessions() as session:
        remaining = (
            (await session.execute(text("SELECT token FROM access_tokens")))
            .scalars()
            .all()
        )
    assert remaining == ["fresh-token"]
    assert await delete_expired_access_tokens(conninfo, lifetime_seconds=LIFETIME) == 0


async def test_stale_codes_and_buckets_are_deleted(
    migrated_dsn: str, database: Database
) -> None:
    conninfo = (
        make_url(migrated_dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    async with database.engine.begin() as connection:
        await connection.execute(text("TRUNCATE one_time_codes, rate_limit_buckets"))
        await connection.execute(
            text(
                "INSERT INTO one_time_codes "
                "(id, purpose, channel, destination, code_hash, expires_at) VALUES "
                "(gen_random_uuid(), 'verify_email', 'email', 'a@b.c', 'x', "
                "now() - interval '2 days'),"
                "(gen_random_uuid(), 'verify_email', 'email', 'a@b.c', 'y', "
                "now() + interval '5 minutes')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO rate_limit_buckets (key, window_start, count) VALUES "
                "('old', now() - interval '2 days', 1), ('new', now(), 1)"
            )
        )

    assert await delete_stale_account_rows(conninfo) == (1, 1)
    assert await delete_stale_account_rows(conninfo) == (0, 0)
