"""Publishing authored content through a background job (spec §5.1, §5.3).

`publish` records a queued job and hands it to the dispatcher, which runs it later or,
inline, before `publish` answers. `run` does the work when the dispatcher calls back: it
is idempotent, so a retry after a failure resumes the same release, and a call for a
finished job changes nothing.
"""

import logging
import uuid
from dataclasses import replace
from datetime import datetime, timedelta

from pydantic import BaseModel

from pharma_agent.application.corpus.errors import (
    CollectionNotFoundForActor,
    PublishInProgress,
    SystemCollectionReadOnly,
)
from pharma_agent.application.corpus.import_bundle import ImportKnowledgeBundle
from pharma_agent.application.corpus.service import CorpusService
from pharma_agent.application.errors import ForbiddenRole, InvalidInput
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.corpus.authoring import build_bundle
from pharma_agent.domain.corpus.models import (
    Collection,
    NoEarlierRelease,
    ReleaseStatus,
)
from pharma_agent.domain.corpus.ports import CollectionRepository, CorpusRepository
from pharma_agent.domain.corpus.source import (
    IngestJob,
    IngestJobRepository,
    JobConflict,
    JobDispatcher,
    JobStatus,
    JobStep,
    SourceRepository,
)
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import TransactionFactory

STEP_PROGRESS = {
    JobStep.BUNDLE: 5,
    JobStep.CHUNK: 15,
    JobStep.EMBED: 30,
    JobStep.INDEX: 80,
    JobStep.PUBLISH: 95,
}
ERROR_MAX_CHARS = 500


logger = logging.getLogger(__name__)


class JobView(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    status: JobStatus
    step: JobStep
    progress: int
    error: str | None
    attempts: int
    release_number: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ReleaseView(BaseModel):
    id: uuid.UUID
    number: int
    status: ReleaseStatus
    created_at: datetime
    published_at: datetime | None
    current: bool


class PublishService:
    def __init__(
        self,
        *,
        collections: CollectionRepository,
        sources: SourceRepository,
        jobs: IngestJobRepository,
        corpus: CorpusRepository,
        importer: ImportKnowledgeBundle,
        releases: CorpusService,
        dispatcher: JobDispatcher,
        audit: AuditLog,
        tx: TransactionFactory,
        clock: Clock,
        max_attempts: int = 3,
        stale_after: timedelta,
    ) -> None:
        self._collections = collections
        self._sources = sources
        self._jobs = jobs
        self._corpus = corpus
        self._importer = importer
        self._releases = releases
        self._dispatcher = dispatcher
        self._audit = audit
        self._tx = tx
        self._clock = clock
        self._max_attempts = max_attempts
        # An open job older than this has no runner left (crash, lost task, timeout).
        self._stale_after = stale_after

    async def _view(self, job: IngestJob) -> JobView:
        number = None
        if job.release_id is not None:
            release = await self._corpus.get_release(job.release_id)
            number = None if release is None else release.number
        return JobView(
            id=job.id,
            collection_id=job.collection_id,
            status=job.status,
            step=job.step,
            progress=job.progress,
            error=job.error,
            attempts=job.attempts,
            release_number=number,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    async def _visible(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._collections.get(collection_id)
        if collection is None or not policy.can_view_collection(actor, collection):
            raise CollectionNotFoundForActor(str(collection_id))
        return collection

    async def _writable(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._visible(actor, collection_id)
        if collection.is_system:
            raise SystemCollectionReadOnly(
                "the system corpus is imported, not published"
            )
        if not policy.can_edit_collection(actor, collection):
            raise ForbiddenRole("your role cannot publish this collection")
        return collection

    async def publish(self, actor: Actor, collection_id: uuid.UUID) -> JobView:
        await self._writable(actor, collection_id)
        if await self._sources.count_documents(collection_id) == 0:
            raise InvalidInput("add a document before publishing")
        open_job = await self._jobs.open_for(collection_id)
        if open_job is not None:
            if not self._is_stale(open_job):
                raise PublishInProgress("the collection is already being published")
            await self._jobs.update(
                replace(
                    open_job,
                    status=JobStatus.FAILED,
                    error="STALE: no runner finished the job",
                    finished_at=self._clock.now(),
                )
            )
        job = IngestJob(
            id=uuid.uuid4(),
            collection_id=collection_id,
            release_id=None,
            status=JobStatus.QUEUED,
            step=JobStep.BUNDLE,
            progress=0,
            error=None,
            requested_by=actor.user_id,
            attempts=0,
            created_at=self._clock.now(),
            started_at=None,
            finished_at=None,
        )
        try:
            async with self._tx.begin() as tx:
                await self._jobs.create(job, tx)
        except JobConflict as exc:
            raise PublishInProgress(
                "the collection is already being published"
            ) from exc
        # After the commit, so the runner always finds the job. A job nothing will run must
        # not hold the collection's single open slot.
        try:
            await self._dispatcher.enqueue(job.id)
        except Exception:
            await self._jobs.update(
                replace(
                    job,
                    status=JobStatus.FAILED,
                    error="DISPATCH_FAILED: the job could not be queued",
                    finished_at=self._clock.now(),
                )
            )
            raise
        # The dispatcher may have started or, inline, finished the job: report its state.
        return await self._view(await self._jobs.get(job.id) or job)

    def _is_stale(self, job: IngestJob) -> bool:
        started = job.started_at or job.created_at
        return self._clock.now() - started > self._stale_after

    async def recent(self, actor: Actor, *, limit: int) -> list[JobView]:
        if not actor.is_superadmin:
            raise ForbiddenRole("only superadmins list every job")
        return [
            await self._view(job) for job in await self._jobs.list_recent(limit=limit)
        ]

    async def get_job(self, actor: Actor, job_id: uuid.UUID) -> JobView:
        job = await self._jobs.get(job_id)
        if job is None:
            raise CollectionNotFoundForActor(str(job_id))
        await self._visible(actor, job.collection_id)
        return await self._view(job)

    async def run(self, job_id: uuid.UUID) -> JobView:
        """Do the job. Raises while retries remain, so the dispatcher runs it again."""
        job = await self._jobs.get(job_id)
        if job is None:
            raise InvalidInput(f"job {job_id} does not exist")
        if not job.is_open:
            return await self._view(job)
        job = replace(
            job,
            status=JobStatus.RUNNING,
            step=JobStep.BUNDLE,
            progress=STEP_PROGRESS[JobStep.BUNDLE],
            attempts=job.attempts + 1,
            started_at=job.started_at or self._clock.now(),
            error=None,
        )
        await self._jobs.update(job)
        try:
            job = await self._import(job)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:ERROR_MAX_CHARS]
            if job.attempts < self._max_attempts:
                await self._jobs.update(
                    replace(job, status=JobStatus.QUEUED, error=error)
                )
                raise
            failed = replace(
                job,
                status=JobStatus.FAILED,
                error=error,
                finished_at=self._clock.now(),
            )
            await self._jobs.update(failed)
            return await self._view(failed)
        return await self._view(job)

    async def _import(self, job: IngestJob) -> IngestJob:
        collection = await self._collections.get(job.collection_id)
        if collection is None:
            raise InvalidInput("the collection was deleted")
        bundle = build_bundle(
            collection,
            await self._sources.list_documents(collection.id),
            await self._sources.glossary(collection.id),
            await self._sources.colloquial(collection.id),
        )
        current = job

        async def on_step(step: JobStep) -> None:
            nonlocal current
            current = replace(current, step=step, progress=STEP_PROGRESS[step])
            await self._jobs.update(current)

        report = await self._importer(
            bundle, embeddings=lambda _model, _dims: {}, publish=True, on_step=on_step
        )
        done = replace(
            current,
            status=JobStatus.READY,
            step=JobStep.PUBLISH,
            progress=100,
            release_id=report.release.id,
            finished_at=self._clock.now(),
        )
        await self._jobs.update(done)
        event = new_event(
            Actor(job.requested_by or uuid.UUID(int=0), False, {}),
            AuditAction.COLLECTION_PUBLISHED,
            self._clock.now(),
            organization_id=collection.owner_organization_id,
            subject_user_id=collection.owner_user_id,
            collection_id=collection.id,
            title=collection.title,
            release=report.release.number,
            outcome=report.outcome.value,
        )
        if job.requested_by is None:
            # The requester's account is gone; the event keeps no actor.
            event = replace(event, actor_user_id=None)
        try:
            async with self._tx.begin() as tx:
                await self._audit.record(event, tx)
        except Exception:
            # The release is live; a lost log line must not turn the job back to a retry.
            logger.exception("could not record the publish of job %s", job.id)
        return done

    async def releases(
        self, actor: Actor, collection_id: uuid.UUID
    ) -> list[ReleaseView]:
        collection = await self._visible(actor, collection_id)
        return [
            ReleaseView(
                id=summary.release.id,
                number=summary.release.number,
                status=summary.release.status,
                created_at=summary.release.created_at,
                published_at=summary.release.published_at,
                current=summary.current,
            )
            for summary in await self._corpus.list_releases(collection.key)
        ]

    async def rollback(self, actor: Actor, collection_id: uuid.UUID) -> ReleaseView:
        collection = await self._writable(actor, collection_id)
        try:
            release = await self._releases.rollback(collection.key)
        except NoEarlierRelease as exc:
            raise InvalidInput("there is no earlier release to go back to") from exc
        async with self._tx.begin() as tx:
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.COLLECTION_ROLLED_BACK,
                    self._clock.now(),
                    organization_id=collection.owner_organization_id,
                    subject_user_id=collection.owner_user_id,
                    collection_id=collection.id,
                    title=collection.title,
                    release=release.number,
                ),
                tx,
            )
        return ReleaseView(
            id=release.id,
            number=release.number,
            status=release.status,
            created_at=release.created_at,
            published_at=release.published_at,
            current=True,
        )
