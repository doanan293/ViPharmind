"""The signed-in user's own activity log."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from pharma_agent.api.deps import ActorDependency, ContainerDep, require_organizations
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.access.service import Actor
from pharma_agent.application.audit.service import AuditPage


def build_audit_router(current_actor: ActorDependency) -> APIRouter:
    router = APIRouter(tags=["audit"])
    CurrentActor = Annotated[Actor, Depends(current_actor)]

    @router.get(
        "/account/audit", name="audit:mine", responses=problem_responses(401, 422)
    )
    async def my_audit(
        actor: CurrentActor,
        container: ContainerDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
    ) -> AuditPage:
        return await require_organizations(container).audit.mine(
            actor, limit=limit, cursor=cursor
        )

    return router
