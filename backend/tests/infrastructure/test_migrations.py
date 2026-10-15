import asyncio
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from pharma_agent.infrastructure.persistence.postgres.alembic_config import (
    alembic_config,
)
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    CORPUS_SCHEMA,
)
from pharma_agent.infrastructure.persistence.postgres.metadata import (
    include_name,
    target_metadata,
)

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "one_time_codes",
    "rate_limit_buckets",
    "user",
    "oauth_account",
    "access_tokens",
    "conversations",
    "messages",
    "message_citations",
    "organizations",
    "organization_members",
    "organization_invitations",
    "audit_events",
}
EXPECTED_CORPUS_TABLES = {
    "collections",
    "documents",
    "sections",
    "chunk_versions",
    "releases",
    "release_chunks",
    "source_documents",
    "glossary_entries",
    "colloquial_mappings",
    "ingest_jobs",
}


def _diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "include_schemas": True,
            "include_name": include_name,
        },
    )
    return list(compare_metadata(context, target_metadata))


def _tables(connection: Connection, schema: str | None = None) -> set[str]:
    return set(inspect(connection).get_table_names(schema=schema))


def _schemas(connection: Connection) -> set[str]:
    return set(inspect(connection).get_schema_names())


async def test_upgrade_head_matches_the_models(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        assert await connection.run_sync(_tables) >= EXPECTED_TABLES
        assert (
            await connection.run_sync(_tables, CORPUS_SCHEMA) == EXPECTED_CORPUS_TABLES
        )
        assert await connection.run_sync(_diff) == []
    await engine.dispose()


async def test_downgrade_then_upgrade_round_trips(fresh_database_dsn: str) -> None:
    config = alembic_config(fresh_database_dsn)
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "base")
    engine = create_async_engine(fresh_database_dsn)
    async with engine.connect() as connection:
        assert not (EXPECTED_TABLES & await connection.run_sync(_tables))
        assert CORPUS_SCHEMA not in await connection.run_sync(_schemas)
    await engine.dispose()
    await asyncio.to_thread(command.upgrade, config, "head")


CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


async def test_upgrade_drops_leftover_langgraph_checkpoint_tables(
    fresh_database_dsn: str,
) -> None:
    config = alembic_config(fresh_database_dsn)
    await asyncio.to_thread(command.upgrade, config, "0009")
    engine = create_async_engine(fresh_database_dsn)
    async with engine.begin() as connection:
        for table in CHECKPOINT_TABLES:
            await connection.exec_driver_sql(f"CREATE TABLE {table} (id int)")
    await asyncio.to_thread(command.upgrade, config, "head")
    async with engine.connect() as connection:
        assert not (CHECKPOINT_TABLES & await connection.run_sync(_tables))
    await engine.dispose()


def _indexes(connection: Connection, table: str) -> dict[str | None, list[str | None]]:
    return {
        index["name"]: list(index["column_names"])
        for index in inspect(connection).get_indexes(table)
    }


async def test_keyset_indexes_cover_the_sort_keys(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        conversations = await connection.run_sync(_indexes, "conversations")
        messages = await connection.run_sync(_indexes, "messages")
    await engine.dispose()
    assert conversations["ix_conversations_user_updated_id"] == [
        "user_id",
        "updated_at",
        "id",
    ]
    assert "ix_conversations_user_updated" not in conversations
    assert messages["ix_messages_conversation_created_id"] == [
        "conversation_id",
        "created_at",
        "id",
    ]
    assert "ix_messages_conversation_created" not in messages


def _columns(
    connection: Connection, table: str, schema: str | None = None
) -> dict[str, bool]:
    return {
        column["name"]: column["nullable"]
        for column in inspect(connection).get_columns(table, schema=schema)
    }


async def test_account_columns_exist(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        users = await connection.run_sync(_columns, "user")
        tokens = await connection.run_sync(_columns, "access_tokens")
    await engine.dispose()
    assert users["email"] is True
    assert {"phone_number", "email_verified_at", "phone_verified_at"} <= users.keys()
    assert users["password_set"] is False
    assert {"user_agent", "ip_address", "last_used_at"} <= tokens.keys()


async def test_a_user_needs_an_email_or_a_phone(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_user_email_or_phone"):
            await connection.exec_driver_sql(
                'INSERT INTO "user" (id, hashed_password, is_active, is_superuser, '
                "is_verified) VALUES (gen_random_uuid(), 'x', true, false, false)"
            )
    await engine.dispose()


async def test_emails_are_unique_ignoring_case(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    insert = (
        'INSERT INTO "user" (id, email, hashed_password, is_active, is_superuser, '
        "is_verified) VALUES (gen_random_uuid(), '{}', 'x', true, false, false)"
    )
    async with engine.connect() as connection:
        await connection.exec_driver_sql(insert.format("Case.Dup@Example.com"))
        with pytest.raises(IntegrityError, match="uq_user_email_lower"):
            await connection.exec_driver_sql(insert.format("case.dup@example.com"))
        await connection.rollback()
    await engine.dispose()


async def test_corpus_cleanup_dropped_the_cache_and_the_embedding_text(
    migrated_dsn: str,
) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        corpus_tables = await connection.run_sync(_tables, CORPUS_SCHEMA)
        columns = await connection.run_sync(_columns, "chunk_versions", CORPUS_SCHEMA)
        public_tables = await connection.run_sync(_tables)
    await engine.dispose()
    assert "embedding_cache" not in corpus_tables
    assert "embedding_text" not in columns
    assert "embedding_text_sha256" in columns
    assert "skills" not in public_tables


async def test_one_open_invitation_per_email_and_organization(
    migrated_dsn: str,
) -> None:
    engine = create_async_engine(migrated_dsn)
    org, user = uuid.uuid4(), uuid.uuid4()
    insert = text(
        "INSERT INTO organization_invitations (id, organization_id, email, role,"
        " invited_by, status, token_hash, created_at) VALUES (gen_random_uuid(),"
        " :org, 'a@b.c', 'member', :user, :status, md5(random()::text), now())"
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                'INSERT INTO "user" (id, email, hashed_password, is_active,'
                " is_superuser, is_verified) VALUES (:id, :email, 'x', true, false,"
                " true)"
            ),
            {"id": user, "email": f"{user.hex}@example.com"},
        )
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, created_at, updated_at)"
                " VALUES (:id, 'Org', now(), now())"
            ),
            {"id": org},
        )
        await connection.execute(insert, {"org": org, "user": user, "status": "sent"})
        await connection.execute(
            insert, {"org": org, "user": user, "status": "declined"}
        )
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(
                    insert, {"org": org, "user": user, "status": "pending_approval"}
                )
    await engine.dispose()


async def test_quota_columns_exist(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        users = await connection.run_sync(_columns, "user")
        organizations = await connection.run_sync(_columns, "organizations")
    await engine.dispose()
    for columns in (users, organizations):
        assert columns["text_quota_bytes"] and columns["collection_quota"]


async def test_collection_owner_and_visibility_constraints(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    user, org = uuid.uuid4(), uuid.uuid4()
    insert = text(
        "INSERT INTO corpus.collections (id, key, title, owner_user_id,"
        " owner_organization_id, visibility) VALUES (gen_random_uuid(), :key, 't',"
        " :u, :o, :v)"
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                'INSERT INTO "user" (id, email, hashed_password, is_active,'
                " is_superuser, is_verified) VALUES (:id, :email, 'x', true, false,"
                " true)"
            ),
            {"id": user, "email": f"{user.hex}@example.com"},
        )
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, created_at, updated_at)"
                " VALUES (:id, 'Org', now(), now())"
            ),
            {"id": org},
        )
        suffix = user.hex[:8]
        valid = [
            (f"sys-{suffix}", None, None, "public"),
            (f"mine-{suffix}", user, None, "private"),
            (f"org-{suffix}", None, org, "organization"),
        ]
        for key, owner_user, owner_org, visibility in valid:
            await connection.execute(
                insert, {"key": key, "u": owner_user, "o": owner_org, "v": visibility}
            )
        invalid = [
            (f"both-{suffix}", user, org, "private"),
            (f"sys-private-{suffix}", None, None, "private"),
            (f"user-org-{suffix}", user, None, "organization"),
        ]
        for key, owner_user, owner_org, visibility in invalid:
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        insert,
                        {"key": key, "u": owner_user, "o": owner_org, "v": visibility},
                    )
        columns = await connection.run_sync(_columns, "conversations")
    await engine.dispose()
    assert columns["collection_ids"] is True


async def test_one_open_ingest_job_per_collection(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    collection = uuid.uuid4()
    insert = text(
        "INSERT INTO corpus.ingest_jobs (id, collection_id, status, step, progress,"
        " attempts, created_at) VALUES (gen_random_uuid(), :c, :status, 'bundle', 0,"
        " 0, now())"
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO corpus.collections (id, key, title, visibility)"
                " VALUES (:id, :key, 't', 'public')"
            ),
            {"id": collection, "key": f"jobs-{collection.hex[:8]}"},
        )
        await connection.execute(insert, {"c": collection, "status": "ready"})
        await connection.execute(insert, {"c": collection, "status": "queued"})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(insert, {"c": collection, "status": "running"})
    await engine.dispose()
