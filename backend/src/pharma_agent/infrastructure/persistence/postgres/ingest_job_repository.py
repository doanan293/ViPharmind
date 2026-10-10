"""IngestJobRepository over `corpus.ingest_jobs`."""

import uuid

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.corpus.source import (
    OPEN_JOB_STATUSES,
    IngestJob,
    JobConflict,
    JobStatus,
    JobStep,
)
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    IngestJobTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_job = IngestJobTable.__table__.c


def _ingest_job(row: IngestJobTable) -> IngestJob:
    return IngestJob(
        id=row.id,
        collection_id=row.collection_id,
        release_id=row.release_id,
        status=JobStatus(row.status),
        step=JobStep(row.step),
        progress=row.progress,
        error=row.error,
        requested_by=row.requested_by,
        attempts=row.attempts,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _values(job: IngestJob) -> dict[str, object]:
    return {
        "release_id": job.release_id,
        "status": job.status.value,
        "step": job.step.value,
        "progress": job.progress,
        "error": job.error,
        "attempts": job.attempts,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


class PostgresIngestJobRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, job_id: uuid.UUID) -> IngestJob | None:
        async with self._sessions() as session:
            row = await session.get(IngestJobTable, job_id)
        return None if row is None else _ingest_job(row)

    async def open_for(self, collection_id: uuid.UUID) -> IngestJob | None:
        query = select(IngestJobTable).where(
            _job.collection_id == collection_id,
            _job.status.in_([status.value for status in OPEN_JOB_STATUSES]),
        )
        async with self._sessions() as session:
            row = (await session.scalars(query)).first()
        return None if row is None else _ingest_job(row)

    async def create(self, job: IngestJob, tx: Transaction) -> None:
        session = session_of(tx)
        try:
            async with session.begin_nested():
                await session.execute(
                    insert(IngestJobTable).values(
                        id=job.id,
                        collection_id=job.collection_id,
                        requested_by=job.requested_by,
                        created_at=job.created_at,
                        **_values(job),
                    )
                )
        except IntegrityError as exc:
            raise JobConflict("the collection is already being published") from exc

    async def update(self, job: IngestJob) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(IngestJobTable).where(_job.id == job.id).values(**_values(job))
            )

    async def list_recent(self, *, limit: int) -> list[IngestJob]:
        query = (
            select(IngestJobTable)
            .order_by(_job.created_at.desc(), _job.id.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [_ingest_job(row) for row in rows]
