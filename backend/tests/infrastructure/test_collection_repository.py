import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, text

from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    Visibility,
    collection_id_for,
)
from pharma_agent.domain.organizations.models import Organization
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.tables import UserTable
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)

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


def collection(
    key: str,
    *,
    user: uuid.UUID | None = None,
    org: uuid.UUID | None = None,
    visibility: Visibility = Visibility.PRIVATE,
) -> Collection:
    return Collection(
        id=collection_id_for(key),
        key=key,
        title=key,
        owner_user_id=user,
        owner_organization_id=org,
        visibility=visibility,
    )


async def test_visibility_follows_membership_and_deletion_hides(
    database: Database,
) -> None:
    repo = PostgresCollectionRepository(database.sessions)
    orgs = PostgresOrganizationRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    a, b = await add_user(database), await add_user(database)
    org = Organization(uuid.uuid4(), "Org", None, None, NOW, NOW)
    rows = [
        collection("sys", visibility=Visibility.PUBLIC),
        collection("a-private", user=a),
        collection("b-private", user=b),
        collection("org-draft", org=org.id),
        collection("org-shared", org=org.id, visibility=Visibility.ORGANIZATION),
    ]
    async with tx.begin() as t:
        await orgs.create(org, a, t)
        for row in rows:
            await repo.create(row, NOW, t)

    def keys(found: list[Collection]) -> set[str]:
        return {c.key for c in found}

    owner = Actor(a, False, {org.id: Role.OWNER})
    member = Actor(b, False, {org.id: Role.MEMBER})
    admin = Actor(uuid.uuid4(), True, {})
    assert keys(await repo.visible_for(owner)) == {
        "sys",
        "a-private",
        "org-draft",
        "org-shared",
    }
    assert keys(await repo.visible_for(member)) == {"sys", "b-private", "org-shared"}
    assert len(await repo.visible_for(admin)) == 5
    assert await repo.count_owned(CollectionOwner(organization_id=org.id)) == 2
    stored = await repo.get(collection_id_for("org-shared"))
    assert stored is not None and stored.owner_organization_id == org.id

    async with tx.begin() as t:
        await repo.set_visibility(
            collection_id_for("org-draft"), Visibility.ORGANIZATION, NOW, t
        )
        await repo.rename(collection_id_for("a-private"), "Renamed", NOW, t)
        await repo.mark_deleted(collection_id_for("org-shared"), NOW, t)
    assert keys(await repo.visible_for(member)) == {"sys", "b-private", "org-draft"}
    assert await repo.get(collection_id_for("org-shared")) is None
    renamed = await repo.get(collection_id_for("a-private"))
    assert renamed is not None and renamed.title == "Renamed"


async def test_deleting_an_organization_marks_its_collections_deleted(
    database: Database,
) -> None:
    repo = PostgresCollectionRepository(database.sessions)
    orgs = PostgresOrganizationRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    a = await add_user(database)
    org = Organization(uuid.uuid4(), "Org", None, None, NOW, NOW)
    async with tx.begin() as t:
        await orgs.create(org, a, t)
        await repo.create(collection("o1", org=org.id), NOW, t)
    async with tx.begin() as t:
        await orgs.delete(org.id, t)
    assert await repo.get(collection_id_for("o1")) is None
    assert await repo.visible_for(Actor(uuid.uuid4(), True, {})) == []
