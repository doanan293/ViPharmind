import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, text

from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import AccountConflict, OtpPurpose
from pharma_agent.domain.shared.clock import FixedClock
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.one_time_codes import (
    PostgresOneTimeCodeStore,
)
from pharma_agent.infrastructure.persistence.postgres.rate_limiter import (
    PostgresRateLimiter,
)
from pharma_agent.infrastructure.persistence.postgres.session_store import (
    PostgresSessionStore,
)
from pharma_agent.infrastructure.persistence.postgres.tables import (
    AccessTokenTable,
    OAuthAccountTable,
    UserTable,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def database(migrated_dsn: str) -> AsyncIterator[Database]:
    db = Database(migrated_dsn, pool_size=2)
    async with db.engine.begin() as connection:
        await connection.execute(
            text('TRUNCATE "user", one_time_codes, rate_limit_buckets CASCADE')
        )
    yield db
    await db.dispose()


async def add_user(db: Database, email: str | None, **values: object) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(UserTable).values(
                id=user_id,
                email=email,
                hashed_password="hash",
                is_active=True,
                is_superuser=False,
                is_verified=False,
                **values,
            )
        )
    return user_id


async def test_get_by_email_ignores_case(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "An@Example.com")
    found = await repo.get_by_email("an@example.COM")
    assert found is not None and found.id == user_id
    assert found.email_verified is False and found.password_set is True


async def test_phone_user_round_trip_and_conflicts(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user = await repo.create_phone_user(
        phone="+84912345678", hashed_password="h", now=NOW
    )
    assert user.email is None and user.phone_verified and not user.password_set
    with pytest.raises(AccountConflict):
        await repo.create_phone_user(phone="+84912345678", hashed_password="h", now=NOW)
    other = await add_user(database, "bo@example.com")
    with pytest.raises(AccountConflict):
        await repo.set_phone(other, "+84912345678", NOW)


async def test_updates_mark_verified_and_password(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "an@example.com", password_set=False)
    await repo.mark_email_verified(user_id, NOW)
    await repo.set_password(user_id, "new-hash")
    await repo.update_display_name(user_id, "An")
    user = await repo.get(user_id)
    assert user is not None and user.email_verified and user.password_set
    assert user.display_name == "An"
    assert await repo.hashed_password(user_id) == "new-hash"
    taken = await add_user(database, "bo@example.com")
    with pytest.raises(AccountConflict):
        await repo.set_email(taken, "an@example.com", NOW)


async def test_unlink_oauth_removes_the_google_account(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "an@example.com")
    async with database.sessions.begin() as session:
        await session.execute(
            insert(OAuthAccountTable).values(
                id=uuid.uuid4(),
                user_id=user_id,
                oauth_name="google",
                access_token="t",
                account_id="g-1",
                account_email="an@example.com",
            )
        )
    linked = await repo.get(user_id)
    assert linked is not None and linked.google_linked
    await repo.unlink_oauth(user_id, "google")
    unlinked = await repo.get(user_id)
    assert unlinked is not None and not unlinked.google_linked


async def test_issue_replaces_unused_codes_and_find_respects_limits(
    database: Database,
) -> None:
    store = PostgresOneTimeCodeStore(database.sessions)
    kwargs = {
        "purpose": OtpPurpose.VERIFY_EMAIL,
        "destination": "an@example.com",
        "user_id": None,
        "expires_at": NOW + timedelta(minutes=10),
        "now": NOW,
    }
    first = await store.issue(digest="a" * 64, **kwargs)
    second = await store.issue(digest="b" * 64, **kwargs)
    active = await store.find_active(OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW)
    assert active is not None and active.id == second and active.id != first
    assert (
        await store.find_active(
            OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW + timedelta(minutes=11)
        )
        is None
    )
    for _ in range(MAX_ATTEMPTS):
        await store.record_failure(second)
    assert (
        await store.find_active(OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW) is None
    )


async def test_consume_succeeds_once(database: Database) -> None:
    store = PostgresOneTimeCodeStore(database.sessions)
    code_id = await store.issue(
        purpose=OtpPurpose.PHONE_LOGIN,
        destination="+84912345678",
        user_id=None,
        digest="c" * 64,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    results = await asyncio.gather(
        store.consume(code_id, NOW), store.consume(code_id, NOW)
    )
    assert sorted(results) == [False, True]


async def test_rate_limiter_counts_per_window(database: Database) -> None:
    clock = FixedClock(NOW + timedelta(seconds=30))
    limiter = PostgresRateLimiter(database.sessions, clock)
    assert await limiter.hit("k", limit=2, window_seconds=60) is None
    assert await limiter.hit("k", limit=2, window_seconds=60) is None
    assert await limiter.check("k", limit=2, window_seconds=60) == pytest.approx(30)
    assert await limiter.hit("k", limit=2, window_seconds=60) == pytest.approx(30)
    assert await limiter.check("other", limit=2, window_seconds=60) is None
    later = PostgresRateLimiter(
        database.sessions, FixedClock(NOW + timedelta(seconds=61))
    )
    assert await later.check("k", limit=2, window_seconds=60) is None


async def test_session_store_lists_and_deletes(database: Database) -> None:
    user_id = await add_user(database, "an@example.com")
    async with database.sessions.begin() as session:
        for token, age in (("t-old", 10), ("t-new", 1), ("t-expired", 9999)):
            await session.execute(
                insert(AccessTokenTable).values(
                    token=token,
                    user_id=user_id,
                    created_at=NOW - timedelta(hours=age),
                    user_agent="Firefox",
                    ip_address="10.0.0.1",
                )
            )
    store = PostgresSessionStore(
        database.sessions, lifetime_seconds=7 * 24 * 3600, clock=FixedClock(NOW)
    )
    assert [record.token for record in await store.for_user(user_id)] == [
        "t-new",
        "t-old",
    ]
    assert await store.delete(user_id, "t-old") is True
    assert await store.delete(user_id, "t-old") is False
    assert await store.delete_all(user_id, keep="t-new") == 1  # only t-expired remained
    assert [record.token for record in await store.for_user(user_id)] == ["t-new"]
