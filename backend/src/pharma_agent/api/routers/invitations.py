"""The invited person's side: preview (public), accept and decline."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from pharma_agent.api.deps import ActorDependency, ContainerDep, require_organizations
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor
from pharma_agent.application.organizations.invitations import InvitationPreview
from pharma_agent.application.organizations.service import OrganizationView

Token = Annotated[str, Path(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


def build_invitations_router(current_actor: ActorDependency) -> APIRouter:
    router = APIRouter(prefix="/invitations", tags=["invitations"])
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get(
        "/{token}", name="invitations:preview", responses=problem_responses(404, 422)
    )
    async def preview_invitation(
        token: Token, container: ContainerDep
    ) -> InvitationPreview:
        return await require_organizations(container).invitations.preview(token)

    @router.post(
        "/{token}/accept",
        name="invitations:accept",
        responses=problem_responses(401, 404, 409, 422),
    )
    async def accept_invitation(
        token: Token, actor: CurrentActor, container: ContainerDep
    ) -> OrganizationView:
        return await require_organizations(container).invitations.accept(actor, token)

    @router.post(
        "/{token}/decline",
        status_code=204,
        name="invitations:decline",
        response_class=Response,
        responses=problem_responses(401, 404, 409, 422),
    )
    async def decline_invitation(
        token: Token, actor: CurrentActor, container: ContainerDep
    ) -> Response:
        await require_organizations(container).invitations.decline(actor, token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
