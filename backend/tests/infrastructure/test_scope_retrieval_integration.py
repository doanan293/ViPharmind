"""The search scope follows visibility and membership, on real Postgres and Qdrant.

Two collections hold different documents: one is A's personal collection, the other belongs
to organization O and is shared with its members. B is a member of O.
"""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy import insert, text

from pharma_agent.application.access.service import ActorResolver
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.corpus.bundle import KnowledgeBundle
from pharma_agent.domain.corpus.models import Visibility
from pharma_agent.domain.organizations.models import Membership, Organization
from pharma_agent.domain.retrieval.models import Query, QueryOrigin
from pharma_agent.domain.retrieval.service import RetrievalService
from pharma_agent.infrastructure.composition import build_retrieval_service
from pharma_agent.infrastructure.corpus_factory import open_corpus_services
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
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
from pharma_agent.infrastructure.retrieval.scope_resolver import PostgresScopeResolver
from tests.corpus_fixtures import (
    small_bundle,
    small_bundle_embeddings,
    with_renamed_documents,
)
from tests.corpus_rows import reset_corpus
from tests.fakes import FakeEmbedder
from tests.infrastructure.test_corpus_retrieval_integration import settings_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
QUERY = [Query(text="paracetamol liều dùng", origin=QueryOrigin.INITIAL)]


@dataclass
class World:
    a: uuid.UUID
    b: uuid.UUID
    org: Organization
    personal: uuid.UUID
    shared: uuid.UUID
    scopes: PostgresScopeResolver
    retrieval: RetrievalService
    organizations: PostgresOrganizationRepository
    tx: PostgresTransactionFactory


def keyed(bundle: KnowledgeBundle, key: str) -> KnowledgeBundle:
    copy = bundle.model_copy(deep=True)
    copy.manifest.collection.key = key
    return copy


async def add_user(database: Database) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with database.sessions.begin() as session:
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


@pytest.fixture
async def world(
    migrated_dsn: str, qdrant_url: str, qdrant_client: AsyncQdrantClient
) -> AsyncIterator[World]:
    database = Database(migrated_dsn, pool_size=2)
    await reset_corpus(database)
    async with database.engine.begin() as connection:
        await connection.execute(text('TRUNCATE "user", organizations CASCADE'))
    a, b = await add_user(database), await add_user(database)
    organizations = PostgresOrganizationRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    org = Organization(uuid.uuid4(), "Khoa Dược", None, None, NOW, NOW)
    async with tx.begin() as t:
        await organizations.create(org, a, t)
        await organizations.add_member(Membership(org.id, b, Role.MEMBER, NOW), t)

    settings = settings_for(migrated_dsn, qdrant_url)
    owner = Actor(a, False, {org.id: Role.OWNER})
    async with open_corpus_services(settings, embedder=FakeEmbedder()) as corpus:
        personal = await corpus.collections.create(
            owner, title="Riêng", owner_organization_id=None
        )
        shared = await corpus.collections.create(
            owner, title="Chung", owner_organization_id=org.id
        )
        await corpus.collections.set_visibility(
            owner, shared.id, Visibility.ORGANIZATION
        )
        for key, bundle in (
            (personal.key, small_bundle()),
            (shared.key, with_renamed_documents(small_bundle(), "-org")),
        ):
            await corpus.importer(
                keyed(bundle, key), embeddings=small_bundle_embeddings, publish=True
            )
    retrieval = build_retrieval_service(settings, embedder=FakeEmbedder())
    try:
        yield World(
            a=a,
            b=b,
            org=org,
            personal=personal.id,
            shared=shared.id,
            scopes=PostgresScopeResolver(
                ActorResolver(
                    PostgresAccountRepository(database.sessions), organizations
                ),
                PostgresCollectionRepository(database.sessions),
            ),
            retrieval=retrieval.service,
            organizations=organizations,
            tx=tx,
        )
    finally:
        await retrieval.aclose()
        await database.dispose()


async def test_users_only_hit_what_they_may_see(world: World) -> None:
    scope_a = await world.scopes.resolve(user_id=world.a.hex, requested=None)
    scope_b = await world.scopes.resolve(user_id=world.b.hex, requested=None)
    assert set(scope_a) == {world.personal, world.shared}
    assert set(scope_b) == {world.shared}

    hits_b = await world.retrieval.search(QUERY, "paracetamol", scope=scope_b)
    assert hits_b.items
    assert {item.hit.collection_id for item in hits_b.items} == {world.shared}


async def test_narrowing_keeps_only_the_requested_collection(world: World) -> None:
    scope = await world.scopes.resolve(user_id=world.a.hex, requested=[world.personal])
    result = await world.retrieval.search(QUERY, "paracetamol", scope=scope)
    assert result.items
    assert {item.hit.collection_id for item in result.items} == {world.personal}


async def test_leaving_the_organization_empties_the_scope_next_turn(
    world: World,
) -> None:
    async with world.tx.begin() as t:
        await world.organizations.remove_member(world.org.id, world.b, t)
    scope = await world.scopes.resolve(user_id=world.b.hex, requested=[world.shared])
    assert scope == {}
    result = await world.retrieval.search(QUERY, "paracetamol", scope=scope)
    assert result.items == [] and result.error is None
