"""Endpoints only the job runner calls; hidden from the OpenAPI document."""

import uuid

from fastapi import APIRouter

from pharma_agent.api.deps import ContainerDep, InternalCaller, require_publishing
from pharma_agent.application.corpus.jobs import JobView


def build_internal_router() -> APIRouter:
    router = APIRouter(prefix="/internal", include_in_schema=False)

    @router.post("/ingest-jobs/{job_id}/run", name="internal:ingest_jobs.run")
    async def run_ingest_job(
        job_id: uuid.UUID, _caller: InternalCaller, container: ContainerDep
    ) -> JobView:
        # Raises while retries remain: the 500 makes Cloud Tasks call again.
        return await require_publishing(container).run(job_id)

    return router
