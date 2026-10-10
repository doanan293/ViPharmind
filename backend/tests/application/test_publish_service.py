import asyncio
import uuid
from collections.abc import Sequence

import pytest

from pharma_agent.application.corpus.collections import CollectionService, QuotaPolicy
from pharma_agent.application.corpus.content import ContentService, DocumentInput
from pharma_agent.application.corpus.errors import PublishInProgress
from pharma_agent.application.corpus.jobs import PublishService
from pharma_agent.application.errors import ForbiddenRole, InvalidInput
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction
from pharma_agent.domain.corpus.models import Visibility
from pharma_agent.domain.corpus.source import JobStatus, JobStep
from pharma_agent.domain.organizations.models import Organization
from pharma_agent.domain.retrieval.ports import RetrievalError
from tests.account_fakes import START, InMemoryAccounts, MutableClock
from tests.collection_fakes import (
    InMemoryCollections,
    InMemoryJobs,
    InMemorySources,
    RecordingDispatcher,
)
from tests.corpus_memory import CorpusAdapters, build_importer, build_release_service
from tests.fakes import FakeEmbedder
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


class BrokenEmbedder(FakeEmbedder):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise RetrievalError("embedding endpoint unavailable")


class World:
    def __init__(self, embedder: FakeEmbedder | None = None) -> None:
        self.clock = MutableClock()
        self.accounts = InMemoryAccounts()
        self.organizations = InMemoryOrganizations(self.accounts)
        self.adapters = CorpusAdapters()
        self.collections = InMemoryCollections(self.adapters.repository)
        self.sources = InMemorySources(self.collections)
        self.jobs = InMemoryJobs()
        self.audit = InMemoryAuditLog()
        self.dispatcher = RecordingDispatcher()
        self.embedder = embedder or FakeEmbedder()
        self.me = self.accounts.add(email="me@example.com").id
        self.org = Organization(uuid.uuid4(), "Org", None, None, START, START)
        self.organizations.organizations[self.org.id] = self.org
        self.organizations.seed_member(self.org.id, self.me, Role.EDITOR)
        tx = InMemoryTransactions()
        common = {
            "organizations": self.organizations,
            "accounts": self.accounts,
            "audit": self.audit,
            "tx": tx,
            "clock": self.clock,
            "quotas": QuotaPolicy(),
        }
        self.collection_service = CollectionService(
            collections=self.collections,
            corpus=self.adapters.repository,
            index=self.adapters.index,
            sources=self.sources,
            **common,
        )
        self.content = ContentService(
            collections=self.collections, sources=self.sources, **common
        )
        self.service = PublishService(
            collections=self.collections,
            sources=self.sources,
            jobs=self.jobs,
            corpus=self.adapters.repository,
            importer=build_importer(self.adapters, self.embedder, clock=self.clock),
            releases=build_release_service(
                self.adapters, self.embedder, clock=self.clock
            ),
            dispatcher=self.dispatcher,
            audit=self.audit,
            tx=tx,
            clock=self.clock,
            max_attempts=2,
        )

    def editor(self) -> Actor:
        return actor(self.me, {self.org.id: Role.EDITOR})

    async def collection_with_a_document(self) -> uuid.UUID:
        view = await self.collection_service.create(
            self.editor(), title="Chung", owner_organization_id=self.org.id
        )
        await self.collection_service.set_visibility(
            self.editor(), view.id, Visibility.ORGANIZATION
        )
        await self.content.create_document(
            self.editor(),
            view.id,
            DocumentInput(title="Paracetamol", markdown="# Liều\n\nNgười lớn 500 mg."),
        )
        return view.id


async def test_publish_queues_a_job_and_running_it_publishes_a_release() -> None:
    w = World()
    collection = await w.collection_with_a_document()
    queued = await w.service.publish(w.editor(), collection)
    assert queued.status is JobStatus.QUEUED
    assert w.dispatcher.enqueued == [queued.id]

    done = await w.service.run(queued.id)
    assert done.status is JobStatus.READY and done.progress == 100
    assert done.step is JobStep.PUBLISH and done.release_number == 1
    view = await w.collection_service.get(w.editor(), collection)
    assert view.current_release_number == 1
    assert w.audit.actions()[-1] is AuditAction.COLLECTION_PUBLISHED
    assert w.adapters.index.points


async def test_running_a_finished_job_again_changes_nothing() -> None:
    w = World()
    collection = await w.collection_with_a_document()
    job = await w.service.publish(w.editor(), collection)
    await w.service.run(job.id)
    stage_calls = w.adapters.repository.stage_calls
    again = await w.service.run(job.id)
    assert again.status is JobStatus.READY
    assert w.adapters.repository.stage_calls == stage_calls


async def test_only_one_job_per_collection_even_in_parallel() -> None:
    w = World()
    collection = await w.collection_with_a_document()
    results = await asyncio.gather(
        w.service.publish(w.editor(), collection),
        w.service.publish(w.editor(), collection),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, PublishInProgress) for r in results) == 1
    assert len(w.jobs.rows) == 1


async def test_failures_retry_then_give_up() -> None:
    w = World(embedder=BrokenEmbedder())
    collection = await w.collection_with_a_document()
    job = await w.service.publish(w.editor(), collection)
    with pytest.raises(RetrievalError):
        await w.service.run(job.id)
    retried = w.jobs.rows[job.id]
    assert retried.status is JobStatus.QUEUED and retried.attempts == 1
    assert retried.error and "unavailable" in retried.error
    failed = await w.service.run(job.id)
    assert failed.status is JobStatus.FAILED and failed.attempts == 2


async def test_publishing_needs_documents_and_edit_rights() -> None:
    w = World()
    empty = await w.collection_service.create(
        w.editor(), title="Trống", owner_organization_id=None
    )
    with pytest.raises(InvalidInput):
        await w.service.publish(w.editor(), empty.id)
    collection = await w.collection_with_a_document()
    member = actor(uuid.uuid4(), {w.org.id: Role.MEMBER})
    with pytest.raises(ForbiddenRole):
        await w.service.publish(member, collection)


async def test_rollback_returns_to_the_previous_release() -> None:
    w = World()
    collection = await w.collection_with_a_document()
    await w.service.run((await w.service.publish(w.editor(), collection)).id)
    w.clock.advance(minutes=1)
    [document] = await w.content.list_documents(w.editor(), collection)
    await w.content.update_document(
        w.editor(),
        collection,
        document.id,
        DocumentInput(title="Paracetamol", markdown="# Liều\n\nNgười lớn 1 g."),
    )
    w.clock.advance(minutes=1)
    second = await w.service.run((await w.service.publish(w.editor(), collection)).id)
    assert second.release_number == 2
    back = await w.service.rollback(w.editor(), collection)
    assert back.number == 1 and back.current
    releases = await w.service.releases(w.editor(), collection)
    assert [(r.number, r.current) for r in releases] == [(2, False), (1, True)]
    assert w.audit.actions()[-1] is AuditAction.COLLECTION_ROLLED_BACK
