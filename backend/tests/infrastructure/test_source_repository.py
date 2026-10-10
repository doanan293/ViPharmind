import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, text

from pharma_agent.domain.corpus.bundle import (
    ColloquialMappingRecord,
    DocumentKind,
    GlossaryEntry,
)
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    collection_id_for,
)
from pharma_agent.domain.corpus.source import (
    DocumentKeyConflict,
    IngestJob,
    JobConflict,
    JobStatus,
    JobStep,
    SourceDocument,
)
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.ingest_job_repository import (
    PostgresIngestJobRepository,
)
from pharma_agent.infrastructure.persistence.postgres.source_repository import (
    PostgresSourceRepository,
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
        await connection.execute(text('TRUNCATE "user", corpus.collections CASCADE'))
    yield db
    await db.dispose()


async def setup(db: Database) -> tuple[uuid.UUID, Collection]:
    user = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(UserTable).values(
                id=user,
                email=f"{user.hex[:8]}@example.com",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
        )
    collection = Collection(
        id=collection_id_for("u-abc"), key="u-abc", title="t", owner_user_id=user
    )
    async with PostgresTransactionFactory(db.sessions).begin() as tx:
        await PostgresCollectionRepository(db.sessions).create(collection, NOW, tx)
    return user, collection


def document(collection: Collection, key: str, text_: str) -> SourceDocument:
    return SourceDocument(
        id=uuid.uuid4(),
        collection_id=collection.id,
        key=key,
        title=key.title(),
        kind=DocumentKind.LEAFLET,
        source_title="",
        source_url=None,
        markdown=text_,
        char_count=len(text_),
        created_by=None,
        created_at=NOW,
        updated_by=None,
        updated_at=NOW,
    )


async def test_documents_metadata_and_text_usage(database: Database) -> None:
    user, collection = await setup(database)
    repo = PostgresSourceRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    first, second = document(collection, "a", "xxxx"), document(collection, "b", "yy")
    async with tx.begin() as t:
        await repo.create_document(first, t)
        await repo.create_document(second, t)
    with pytest.raises(DocumentKeyConflict):
        async with tx.begin() as t:
            await repo.create_document(document(collection, "a", "z"), t)
    assert [d.key for d in await repo.list_documents(collection.id)] == ["a", "b"]
    assert await repo.document_keys(collection.id) == {"a", "b"}
    assert await repo.count_documents(collection.id) == 2
    assert await repo.text_usage(CollectionOwner(user_id=user)) == 6
    async with tx.begin() as t:
        await repo.update_document(replace(first, markdown="x", char_count=1), t)
        await repo.delete_document(second.id, t)
    stored = await repo.get_document(first.id)
    assert stored is not None and stored.markdown == "x"
    assert await repo.text_usage(CollectionOwner(user_id=user)) == 1

    glossary = [
        GlossaryEntry(term="IV", aliases=["tiêm tĩnh mạch"]),
        GlossaryEntry(term="ADR", case_sensitive=True, category="viết tắt"),
    ]
    mappings = [ColloquialMappingRecord(key="hạ sốt", section_keys=["u-abc:a#body"])]
    async with tx.begin() as t:
        await repo.replace_glossary(collection.id, glossary, t)
        await repo.replace_colloquial(collection.id, mappings, t)
    assert await repo.glossary(collection.id) == glossary
    assert await repo.colloquial(collection.id) == mappings
    async with tx.begin() as t:
        await repo.replace_glossary(collection.id, glossary[:1], t)
    assert await repo.glossary(collection.id) == glossary[:1]


async def test_one_open_job_per_collection(database: Database) -> None:
    _, collection = await setup(database)
    jobs = PostgresIngestJobRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    job = IngestJob(
        id=uuid.uuid4(),
        collection_id=collection.id,
        release_id=None,
        status=JobStatus.QUEUED,
        step=JobStep.BUNDLE,
        progress=0,
        error=None,
        requested_by=None,
        attempts=0,
        created_at=NOW,
        started_at=None,
        finished_at=None,
    )
    async with tx.begin() as t:
        await jobs.create(job, t)
    with pytest.raises(JobConflict):
        async with tx.begin() as t:
            await jobs.create(replace(job, id=uuid.uuid4()), t)
    assert await jobs.open_for(collection.id) == job
    done = replace(job, status=JobStatus.READY, progress=100, finished_at=NOW)
    await jobs.update(done)
    assert await jobs.get(job.id) == done
    assert await jobs.open_for(collection.id) is None
    assert await jobs.list_recent(limit=5) == [done]
