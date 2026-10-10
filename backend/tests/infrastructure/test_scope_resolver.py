import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, text, update

from pharma_agent.application.access.service import ActorResolver
from pharma_agent.domain.corpus.models import Collection, Visibility, collection_id_for
from pharma_agent.domain.organizations.models import Organization
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    CollectionTable,
    ReleaseTable,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.tables import UserTable
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)
from pharma_agent.infrastructure.retrieval.scope_resolver import PostgresScopeResolver

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


@pytest.fixture
async def database(migrated_dsn: str) -> AsyncIterator[Database]:
    db = Database(migrated_dsn, pool_size=2)
    async with db.engine.begin() as connection:
        await connection.execute(
            text('TRUNCATE "user", organizations, corpus.collections CASCADE')
        )
    yield db
    await db.dispose()


async def add_user(db: Database) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(UserTable).values(
                id=user_id,
                email=f"{user_id.hex[:8]}@example.com",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
        )
    return user_id


async def add_collection(
    db: Database, collection: Collection, *, published: bool = True
) -> uuid.UUID | None:
    repo = PostgresCollectionRepository(db.sessions)
    async with PostgresTransactionFactory(db.sessions).begin() as tx:
        await repo.create(collection, NOW, tx)
    if not published:
        return None
    release_id = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(ReleaseTable).values(
                id=release_id,
                collection_id=collection.id,
                number=1,
                status="ready",
                bundle_digest="d",
                chunker_version="c",
                embedding_model="m",
            )
        )
        await session.execute(
            update(CollectionTable)
            .where(CollectionTable.id == collection.id)
            .values(current_release_id=release_id)
        )
    return release_id


def col(
    key: str,
    *,
    owner_user_id: uuid.UUID | None = None,
    visibility: Visibility = Visibility.PRIVATE,
) -> Collection:
    return Collection(
        id=collection_id_for(key),
        key=key,
        title=key,
        owner_user_id=owner_user_id,
        visibility=visibility,
    )


async def test_scope_is_what_the_user_may_see_narrowed_by_the_request(
    database: Database,
) -> None:
    me, other = await add_user(database), await add_user(database)
    orgs = PostgresOrganizationRepository(database.sessions)
    org = Organization(uuid.uuid4(), "Org", None, None, NOW, NOW)
    async with PostgresTransactionFactory(database.sessions).begin() as tx:
        await orgs.create(org, other, tx)
    public = await add_collection(database, col("pub", visibility=Visibility.PUBLIC))
    mine = await add_collection(database, col("mine", owner_user_id=me))
    theirs = await add_collection(database, col("theirs", owner_user_id=other))
    await add_collection(
        database, col("unpublished", owner_user_id=me), published=False
    )
    resolver = PostgresScopeResolver(
        ActorResolver(PostgresAccountRepository(database.sessions), orgs),
        PostgresCollectionRepository(database.sessions),
    )

    everything = await resolver.resolve(user_id=me.hex, requested=None)
    assert everything == {
        collection_id_for("pub"): public,
        collection_id_for("mine"): mine,
    }
    narrowed = await resolver.resolve(
        user_id=me.hex,
        requested=[collection_id_for("mine"), collection_id_for("theirs")],
    )
    assert narrowed == {collection_id_for("mine"): mine}
    assert theirs is not None
    assert await resolver.resolve(user_id=me.hex, requested=[uuid.uuid4()]) == {}
