import asyncio
import uuid

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from pharma_agent import cli
from pharma_agent.infrastructure.persistence.postgres.tables import UserTable

pytestmark = pytest.mark.integration

_user = UserTable.__table__.c


async def add_user(dsn: str, user_id: uuid.UUID, email: str) -> None:
    engine = create_async_engine(dsn)
    async with engine.begin() as connection:
        await connection.execute(
            insert(UserTable).values(
                id=user_id,
                email=email,
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
        )
    await engine.dispose()


async def superuser_flag(dsn: str, user_id: uuid.UUID) -> bool:
    engine = create_async_engine(dsn)
    async with engine.connect() as connection:
        flag = (
            await connection.execute(
                select(_user.is_superuser).where(_user.id == user_id)
            )
        ).scalar_one()
    await engine.dispose()
    return flag


def test_grant_and_revoke_superadmin_by_email(
    migrated_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sync on purpose: the CLI runs its own event loop with asyncio.run.
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:8]}@example.com"
    asyncio.run(add_user(migrated_dsn, user_id, email))
    monkeypatch.setenv("PHARMA_POSTGRES__DSN", migrated_dsn)
    runner = CliRunner()

    granted = runner.invoke(cli.app, ["superadmin", "grant", email.upper()])
    assert granted.exit_code == 0, granted.output
    assert asyncio.run(superuser_flag(migrated_dsn, user_id)) is True
    assert email in runner.invoke(cli.app, ["superadmin", "list"]).output
    missing = runner.invoke(cli.app, ["superadmin", "grant", "nobody@example.com"])
    assert missing.exit_code == 1
    revoked = runner.invoke(cli.app, ["superadmin", "revoke", email])
    assert revoked.exit_code == 0, revoked.output
    assert asyncio.run(superuser_flag(migrated_dsn, user_id)) is False
