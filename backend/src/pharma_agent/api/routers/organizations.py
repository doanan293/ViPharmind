"""Organizations, their members, their invitations and their audit log."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, EmailStr, Field

from pharma_agent.api.deps import (
    ActorDependency,
    ContainerDep,
    RequestLocale,
    require_organizations,
)
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor, Role
from pharma_agent.application.audit.service import AuditPage
from pharma_agent.application.organizations.invitations import InvitationView
from pharma_agent.application.organizations.service import (
    MemberItem,
    OrganizationView,
)

MAX_PAGE_SIZE = 100
Cursor = Annotated[str | None, Query(max_length=512)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


class OrganizationName(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DeleteOrganization(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=100)


class RoleBody(BaseModel):
    role: Role


class InvitationBody(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


def no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_organizations_router(current_actor: ActorDependency) -> APIRouter:
    router = APIRouter(
        prefix="/organizations",
        tags=["organizations"],
        responses=problem_responses(401, 403, 404, 422),
    )
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get("", name="organizations:list")
    async def list_organizations(
        actor: CurrentActor, container: ContainerDep
    ) -> list[OrganizationView]:
        return await require_organizations(container).organizations.list_mine(actor)

    @router.post("", status_code=201, name="organizations:create")
    async def create_organization(
        body: OrganizationName, actor: CurrentActor, container: ContainerDep
    ) -> OrganizationView:
        return await require_organizations(container).organizations.create(
            actor, body.name
        )

    @router.get("/{organization_id}", name="organizations:get")
    async def get_organization(
        organization_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> OrganizationView:
        return await require_organizations(container).organizations.get(
            actor, organization_id
        )

    @router.patch("/{organization_id}", name="organizations:rename")
    async def rename_organization(
        organization_id: uuid.UUID,
        body: OrganizationName,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> OrganizationView:
        return await require_organizations(container).organizations.rename(
            actor, organization_id, body.name
        )

    @router.delete(
        "/{organization_id}",
        status_code=204,
        name="organizations:delete",
        response_class=Response,
    )
    async def delete_organization(
        organization_id: uuid.UUID,
        body: DeleteOrganization,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> Response:
        await require_organizations(container).organizations.delete(
            actor, organization_id, confirm_name=body.confirm_name
        )
        return no_content()

    @router.get("/{organization_id}/members", name="organizations:members.list")
    async def list_members(
        organization_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[MemberItem]:
        return await require_organizations(container).organizations.members(
            actor, organization_id
        )

    @router.patch(
        "/{organization_id}/members/{user_id}",
        status_code=204,
        name="organizations:members.set_role",
        response_class=Response,
        responses=problem_responses(409),
    )
    async def set_member_role(
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        body: RoleBody,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> Response:
        await require_organizations(container).organizations.set_role(
            actor, organization_id, user_id, body.role
        )
        return no_content()

    @router.delete(
        "/{organization_id}/members/{user_id}",
        status_code=204,
        name="organizations:members.remove",
        response_class=Response,
        responses=problem_responses(409),
    )
    async def remove_member(
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> Response:
        await require_organizations(container).organizations.remove_member(
            actor, organization_id, user_id
        )
        return no_content()

    @router.post(
        "/{organization_id}/leave",
        status_code=204,
        name="organizations:leave",
        response_class=Response,
        responses=problem_responses(409),
    )
    async def leave_organization(
        organization_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> Response:
        await require_organizations(container).organizations.leave(
            actor, organization_id
        )
        return no_content()

    @router.get("/{organization_id}/invitations", name="invitations:list")
    async def list_invitations(
        organization_id: uuid.UUID, actor: CurrentActor, container: ContainerDep
    ) -> list[InvitationView]:
        return await require_organizations(container).invitations.list(
            actor, organization_id
        )

    @router.post(
        "/{organization_id}/invitations",
        status_code=201,
        name="invitations:create",
        responses=problem_responses(409, 429, 503),
    )
    async def create_invitation(
        organization_id: uuid.UUID,
        body: InvitationBody,
        actor: CurrentActor,
        container: ContainerDep,
        locale: RequestLocale,
    ) -> InvitationView:
        return await require_organizations(container).invitations.invite(
            actor, organization_id, body.email, body.role, locale=locale
        )

    @router.post(
        "/{organization_id}/invitations/{invitation_id}/approve",
        name="invitations:approve",
        responses=problem_responses(409, 429, 503),
    )
    async def approve_invitation(
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
        locale: RequestLocale,
    ) -> InvitationView:
        return await require_organizations(container).invitations.approve(
            actor, organization_id, invitation_id, locale=locale
        )

    @router.post(
        "/{organization_id}/invitations/{invitation_id}/reject",
        name="invitations:reject",
        responses=problem_responses(409),
    )
    async def reject_invitation(
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> InvitationView:
        return await require_organizations(container).invitations.reject(
            actor, organization_id, invitation_id
        )

    @router.post(
        "/{organization_id}/invitations/{invitation_id}/revoke",
        name="invitations:revoke",
        responses=problem_responses(409),
    )
    async def revoke_invitation(
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
    ) -> InvitationView:
        return await require_organizations(container).invitations.revoke(
            actor, organization_id, invitation_id
        )

    @router.post(
        "/{organization_id}/invitations/{invitation_id}/resend",
        name="invitations:resend",
        responses=problem_responses(409, 429, 503),
    )
    async def resend_invitation(
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
        locale: RequestLocale,
    ) -> InvitationView:
        return await require_organizations(container).invitations.resend(
            actor, organization_id, invitation_id, locale=locale
        )

    @router.get("/{organization_id}/audit", name="audit:organization")
    async def organization_audit(
        organization_id: uuid.UUID,
        actor: CurrentActor,
        container: ContainerDep,
        limit: PageSize = 50,
        cursor: Cursor = None,
    ) -> AuditPage:
        return await require_organizations(container).audit.for_organization(
            actor, organization_id, limit=limit, cursor=cursor
        )

    return router
