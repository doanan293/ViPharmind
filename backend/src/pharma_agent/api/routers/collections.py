"""Collections the signed-in user may see, create and manage."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from pharma_agent.api.deps import ActorDependency, ContainerDep, require_collections
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor
from pharma_agent.application.corpus.collections import (
    CollectionGroups,
    CollectionView,
    QuotaUsage,
    Visibility,
)


class CreateCollection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Null creates a personal collection.
    owner_organization_id: uuid.UUID | None = None


class UpdateCollection(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: Visibility | None = None


def build_collections_router(current_actor: ActorDependency) -> APIRouter:
    router = APIRouter(
        prefix="/collections",
        tags=["collections"],
        responses=problem_responses(401, 403, 404, 422),
    )
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get("", name="collections:list")
    async def list_collections(
        actor: CurrentActor, container: ContainerDep
    ) -> CollectionGroups:
        return await require_collections(container).visible(actor)

    @router.post("", status_code=201, name="collections:create")
    async def create_collection(
        body: CreateCollection, actor: CurrentActor, container: ContainerDep
    ) -> CollectionView:
        return await require_collections(container).create(
            actor, title=body.title, owner_organization_id=body.owner_organization_id
        )

    @router.get("/quota", name="collections:quota")
    async def collection_quota(
        actor: CurrentActor,
        container: ContainerDep,
        organization_id: Annotated[uuid.UUID | None, Query()] = None,
    ) -> QuotaUsage:
        return await require_collections(container).quota(
            actor, owner_organization_id=organization_id
        )

    @router.get("/{collection_id}", name="collections:get")
    async def get_collection(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> CollectionView:
        return await require_collections(container).get(actor, collection_id)

    @router.patch("/{collection_id}", name="collections:update")
    async def update_collection(
        collection_id: uuid.UUID,
        body: UpdateCollection,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> CollectionView:
        service = require_collections(container)
        view = await service.get(actor, collection_id)
        if body.title is not None:
            view = await service.rename(actor, collection_id, body.title)
        if body.visibility is not None:
            view = await service.set_visibility(actor, collection_id, body.visibility)
        return view

    @router.delete(
        "/{collection_id}",
        status_code=204,
        name="collections:delete",
        response_class=Response,
    )
    async def delete_collection(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> Response:
        await require_collections(container).delete(actor, collection_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
