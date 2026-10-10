"""Publishing a collection, its releases, and the progress of publish jobs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from pharma_agent.api.deps import ActorDependency, ContainerDep, require_publishing
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor
from pharma_agent.application.corpus.jobs import JobView, ReleaseView


def build_jobs_router(current_actor: ActorDependency) -> APIRouter:
    router = APIRouter(tags=["publishing"], responses=problem_responses(401, 403, 404))
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.post(
        "/collections/{collection_id}/publish",
        status_code=202,
        name="collections:publish",
        responses=problem_responses(409, 422),
    )
    async def publish_collection(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> JobView:
        return await require_publishing(container).publish(actor, collection_id)

    @router.post(
        "/collections/{collection_id}/rollback",
        name="collections:rollback",
        responses=problem_responses(422),
    )
    async def rollback_collection(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> ReleaseView:
        return await require_publishing(container).rollback(actor, collection_id)

    @router.get("/collections/{collection_id}/releases", name="collections:releases")
    async def list_releases(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[ReleaseView]:
        return await require_publishing(container).releases(actor, collection_id)

    @router.get("/ingest-jobs/{job_id}", name="jobs:get")
    async def get_job(
        job_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> JobView:
        return await require_publishing(container).get_job(actor, job_id)

    return router
