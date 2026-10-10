"""PublishService and its job dispatcher over Postgres, Qdrant and an embedder."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.corpus.import_bundle import ImportKnowledgeBundle
from pharma_agent.application.corpus.jobs import JobView, PublishService
from pharma_agent.application.corpus.service import CorpusService
from pharma_agent.domain.corpus.ports import Embedder, VectorIndex
from pharma_agent.domain.corpus.source import JobDispatcher
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.jobs.cloud_tasks import CloudTasksDispatcher
from pharma_agent.infrastructure.jobs.inprocess import InProcessDispatcher
from pharma_agent.infrastructure.persistence.postgres.audit_log import PostgresAuditLog
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.corpus_repository import (
    PostgresCorpusRepository,
)
from pharma_agent.infrastructure.persistence.postgres.ingest_job_repository import (
    PostgresIngestJobRepository,
)
from pharma_agent.infrastructure.persistence.postgres.source_repository import (
    PostgresSourceRepository,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)
from pharma_agent.infrastructure.settings import Settings


@dataclass(frozen=True)
class Publishing:
    service: PublishService
    dispatcher: JobDispatcher


def build_publishing(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    index: VectorIndex,
    embedder: Embedder,
    clock: Clock,
    dispatcher: JobDispatcher | None = None,
) -> Publishing:
    """The in-process dispatcher calls back into the service it serves, so the service
    is bound to it after both exist."""
    corpus = PostgresCorpusRepository(sessions)
    batch = settings.corpus
    bound: list[PublishService] = []

    async def run(job_id: uuid.UUID) -> JobView:
        return await bound[0].run(job_id)

    if dispatcher is None:
        dispatcher = (
            CloudTasksDispatcher(settings.jobs)
            if settings.jobs.dispatcher == "cloud_tasks"
            else InProcessDispatcher(run)
        )
    service = PublishService(
        collections=PostgresCollectionRepository(sessions),
        sources=PostgresSourceRepository(sessions),
        jobs=PostgresIngestJobRepository(sessions),
        corpus=corpus,
        importer=ImportKnowledgeBundle(
            corpus,
            index,
            embedder,
            clock,
            embed_batch_size=batch.embed_batch_size,
            embed_max_concurrent=batch.embed_max_concurrent,
        ),
        releases=CorpusService(
            corpus,
            index,
            embedder,
            clock,
            embed_batch_size=batch.embed_batch_size,
            embed_max_concurrent=batch.embed_max_concurrent,
        ),
        dispatcher=dispatcher,
        audit=PostgresAuditLog(sessions),
        tx=PostgresTransactionFactory(sessions),
        clock=clock,
        max_attempts=settings.jobs.max_attempts,
        # Every attempt may run to the dispatch deadline, plus time for queue backoff.
        stale_after=timedelta(
            seconds=settings.jobs.dispatch_deadline_seconds * settings.jobs.max_attempts
            + 600
        ),
    )
    bound.append(service)
    return Publishing(service=service, dispatcher=dispatcher)
