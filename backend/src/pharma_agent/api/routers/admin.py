"""Superadmin console. Everyone else gets 404, so the console does not show it exists."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from pharma_agent.api.deps import (
    ActorDependency,
    ContainerDep,
    require_collections,
    require_organizations,
    require_publishing,
)
from pharma_agent.api.problems import problem_responses
from pharma_agent.api.schemas import CONVERSATION_ID_PATTERN
from pharma_agent.application.access.service import Actor
from pharma_agent.application.admin.service import (
    AdminOrganizationPage,
    AdminOrganizationView,
    AdminUserPage,
    AdminUserView,
)
from pharma_agent.application.audit.service import AuditPage
from pharma_agent.application.conversation.service import ConversationPage, MessagePage
from pharma_agent.application.corpus.collections import CollectionStats
from pharma_agent.application.corpus.jobs import JobView

PageSize = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=512)]
ConversationId = Annotated[str, Field(pattern=CONVERSATION_ID_PATTERN)]


class UpdateUser(BaseModel):
    """Fields left out stay as they are; a null quota restores the default."""

    is_active: bool | None = None
    text_quota_bytes: int | None = Field(default=None, ge=0)
    collection_quota: int | None = Field(default=None, ge=0)


class UpdateOrganization(BaseModel):
    text_quota_bytes: int | None = Field(default=None, ge=0)
    collection_quota: int | None = Field(default=None, ge=0)


def build_admin_router(current_superadmin: ActorDependency) -> APIRouter:
    router = APIRouter(
        prefix="/admin", tags=["admin"], responses=problem_responses(401, 404, 422)
    )
    Admin = Annotated[Actor, Depends(current_superadmin)]

    @router.get("/users", name="admin:users.list")
    async def list_users(
        actor: Admin,
        container: ContainerDep,
        q: Annotated[str | None, Query(max_length=200)] = None,
        limit: PageSize = 50,
        cursor: Cursor = None,
    ) -> AdminUserPage:
        return await require_organizations(container).admin.users(
            actor, query=q, limit=limit, cursor=cursor
        )

    @router.patch("/users/{user_id}", name="admin:users.update")
    async def update_user(
        user_id: uuid.UUID, body: UpdateUser, actor: Admin, container: ContainerDep
    ) -> AdminUserView:
        admin = require_organizations(container).admin
        sent = body.model_fields_set
        view = await admin.get_user(actor, user_id)
        if "is_active" in sent and body.is_active is not None:
            view = await admin.set_user_active(actor, user_id, active=body.is_active)
        if sent & {"text_quota_bytes", "collection_quota"}:
            view = await admin.set_user_quotas(
                actor,
                user_id,
                text_quota_bytes=body.text_quota_bytes
                if "text_quota_bytes" in sent
                else view.text_quota_bytes,
                collection_quota=body.collection_quota
                if "collection_quota" in sent
                else view.collection_quota,
            )
        return view

    @router.get("/organizations", name="admin:organizations.list")
    async def list_organizations(
        actor: Admin,
        container: ContainerDep,
        limit: PageSize = 50,
        cursor: Cursor = None,
    ) -> AdminOrganizationPage:
        return await require_organizations(container).admin.organizations(
            actor, limit=limit, cursor=cursor
        )

    @router.patch("/organizations/{organization_id}", name="admin:organizations.update")
    async def update_organization(
        organization_id: uuid.UUID,
        body: UpdateOrganization,
        actor: Admin,
        container: ContainerDep,
    ) -> AdminOrganizationView:
        return await require_organizations(container).admin.set_organization_quotas(
            actor,
            organization_id,
            text_quota_bytes=body.text_quota_bytes,
            collection_quota=body.collection_quota,
        )

    @router.get("/collections", name="admin:collections.list")
    async def list_collections(
        actor: Admin, container: ContainerDep
    ) -> list[CollectionStats]:
        return await require_collections(container).overview(actor)

    @router.get("/ingest-jobs", name="admin:ingest_jobs.list")
    async def list_jobs(
        actor: Admin, container: ContainerDep, limit: PageSize = 50
    ) -> list[JobView]:
        return await require_publishing(container).recent(actor, limit=limit)

    @router.get("/users/{user_id}/conversations", name="admin:users.conversations")
    async def user_conversations(
        user_id: uuid.UUID,
        actor: Admin,
        container: ContainerDep,
        limit: PageSize = 20,
        cursor: Cursor = None,
    ) -> ConversationPage:
        # Reading is not audited (spec §2); the privacy policy says so.
        return await container.conversations.list_conversations(
            user_id.hex, limit=limit, cursor=cursor
        )

    @router.get(
        "/users/{user_id}/conversations/{conversation_id}/messages",
        name="admin:conversations.messages",
    )
    async def conversation_messages(
        user_id: uuid.UUID,
        conversation_id: ConversationId,
        actor: Admin,
        container: ContainerDep,
        limit: PageSize = 30,
        cursor: Cursor = None,
    ) -> MessagePage:
        return await container.conversations.list_messages(
            user_id.hex, conversation_id, limit=limit, cursor=cursor
        )

    @router.get("/audit", name="admin:audit")
    async def all_audit(
        actor: Admin,
        container: ContainerDep,
        limit: PageSize = 50,
        cursor: Cursor = None,
    ) -> AuditPage:
        return await require_organizations(container).audit.everything(
            actor, limit=limit, cursor=cursor
        )

    return router
