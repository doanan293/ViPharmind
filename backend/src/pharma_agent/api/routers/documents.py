"""Authored content of a collection: documents, uploads, glossary, colloquial names."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from pharma_agent.api.deps import ActorDependency, ContainerDep, require_content
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor
from pharma_agent.application.corpus.content import (
    MAX_UPLOAD_BYTES,
    ColloquialMappingRecord,
    DocumentDetail,
    DocumentInput,
    DocumentView,
    GlossaryEntry,
    SectionChoice,
    UploadResult,
    read_upload,
)


def build_documents_router(current_actor: ActorDependency) -> APIRouter:
    """Routes for a collection's documents, uploads, glossary and colloquial names."""
    router = APIRouter(
        prefix="/collections/{collection_id}",
        tags=["documents"],
        responses=problem_responses(401, 403, 404, 422),
    )
    _add_document_routes(router, current_actor)
    _add_vocabulary_routes(router, current_actor)
    return router


def _add_document_routes(router: APIRouter, current_actor: ActorDependency) -> None:
    """Register the document list, create, upload, get, update and delete routes.

    Args:
        router: The collection-scoped router the handlers are added to.
        current_actor: Dependency that resolves the calling actor.
    """
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get("/documents", name="documents:list")
    async def list_documents(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[DocumentView]:
        return await require_content(container).list_documents(actor, collection_id)

    @router.post("/documents", status_code=201, name="documents:create")
    async def create_document(
        collection_id: uuid.UUID,
        body: DocumentInput,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> DocumentDetail:
        return await require_content(container).create_document(
            actor, collection_id, body
        )

    @router.post(
        "/documents/upload",
        name="documents:upload",
        responses=problem_responses(413),
    )
    async def upload_document(
        collection_id: uuid.UUID,
        file: Annotated[UploadFile, File()],
        actor: CurrentActor,
        container: ContainerDep,
    ) -> UploadResult:
        # Checks the actor may write here before reading the file.
        await require_content(container).list_documents(actor, collection_id)
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        return read_upload(file.filename or "", data)

    @router.get("/documents/{document_id}", name="documents:get")
    async def get_document(
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> DocumentDetail:
        return await require_content(container).get_document(
            actor, collection_id, document_id
        )

    @router.put("/documents/{document_id}", name="documents:update")
    async def update_document(
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        body: DocumentInput,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> DocumentDetail:
        return await require_content(container).update_document(
            actor, collection_id, document_id, body
        )

    @router.delete(
        "/documents/{document_id}",
        status_code=204,
        name="documents:delete",
        response_class=Response,
    )
    async def delete_document(
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> Response:
        await require_content(container).delete_document(
            actor, collection_id, document_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)


def _add_vocabulary_routes(router: APIRouter, current_actor: ActorDependency) -> None:
    """Register the glossary, colloquial-name and section routes.

    Args:
        router: The collection-scoped router the handlers are added to.
        current_actor: Dependency that resolves the calling actor.
    """
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get("/glossary", name="collections:glossary.get")
    async def get_glossary(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[GlossaryEntry]:
        return await require_content(container).glossary(actor, collection_id)

    @router.put("/glossary", name="collections:glossary.put")
    async def put_glossary(
        collection_id: uuid.UUID,
        body: list[GlossaryEntry],
        actor: CurrentActor,
        container: ContainerDep,
    ) -> list[GlossaryEntry]:
        return await require_content(container).replace_glossary(
            actor, collection_id, body
        )

    @router.get("/colloquial", name="collections:colloquial.get")
    async def get_colloquial(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[ColloquialMappingRecord]:
        return await require_content(container).colloquial(actor, collection_id)

    @router.put("/colloquial", name="collections:colloquial.put")
    async def put_colloquial(
        collection_id: uuid.UUID,
        body: list[ColloquialMappingRecord],
        actor: CurrentActor,
        container: ContainerDep,
    ) -> list[ColloquialMappingRecord]:
        return await require_content(container).replace_colloquial(
            actor, collection_id, body
        )

    @router.get("/sections", name="collections:sections")
    async def list_sections(
        collection_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[SectionChoice]:
        return await require_content(container).sections(actor, collection_id)
