import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.access.service import Actor
from pharma_agent.application.account.messages import (
    Locale,
    locale_from_accept_language,
)
from pharma_agent.application.account.service import AccountService
from pharma_agent.application.chat.service import ChatService
from pharma_agent.application.corpus.collections import CollectionService
from pharma_agent.application.corpus.content import ContentService
from pharma_agent.application.corpus.jobs import PublishService
from pharma_agent.application.errors import (
    AgentUnavailable,
    ServiceNotConfigured,
    ServiceStarting,
)
from pharma_agent.application.feedback.service import FeedbackService
from pharma_agent.infrastructure.auth.client_ip import request_client_ip
from pharma_agent.infrastructure.auth.users import (
    SESSION_COOKIE_NAME,
    Auth,
    SessionLogin,
)
from pharma_agent.infrastructure.container import Container
from pharma_agent.infrastructure.jobs.internal_auth import (
    InternalAuthError,
    verify_internal_request,
)
from pharma_agent.infrastructure.organizations_factory import OrganizationServices
from pharma_agent.infrastructure.persistence.postgres.tables import UserTable

UserIdDependency = Callable[..., Awaitable[str]]


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, Container):
        raise ServiceStarting("the service is starting")
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions = get_container(request).sessions
    if sessions is None:
        raise ServiceNotConfigured("the database is not configured")
    return sessions


def require_chat(container: Container) -> ChatService:
    if container.chat is None:
        raise AgentUnavailable(
            "the agent is not configured (set PHARMA_LLM__DEFAULT__API_KEY)"
        )
    return container.chat


def require_feedback(container: Container) -> FeedbackService:
    if container.feedback is None:
        raise ServiceNotConfigured("feedback is not configured")
    return container.feedback


def user_id_dependency(auth: Auth) -> UserIdDependency:
    async def current_user_id(
        user: Annotated[UserTable, Depends(auth.current_active_user)],
    ) -> str:
        return user.id.hex

    return current_user_id


ActorDependency = Callable[..., Awaitable[Actor]]


def require_content(container: Container) -> ContentService:
    if container.content is None:
        raise ServiceNotConfigured("authoring is not configured")
    return container.content


def require_publishing(container: Container) -> PublishService:
    if container.publishing is None:
        raise ServiceNotConfigured("publishing is not configured")
    return container.publishing.service


def verify_internal_caller(request: Request) -> None:
    """Only the job runner, holding the internal token, may call /internal."""
    try:
        verify_internal_request(request.headers, request.app.state.jobs_settings)
    except InternalAuthError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED") from exc


InternalCaller = Annotated[None, Depends(verify_internal_caller)]


def require_collections(container: Container) -> CollectionService:
    if container.collections is None:
        raise ServiceNotConfigured("collections are not configured")
    return container.collections


def require_organizations(container: Container) -> OrganizationServices:
    if container.organizations is None:
        raise ServiceNotConfigured("organizations are not configured")
    return container.organizations


def actor_dependency(current_user_id: UserIdDependency) -> ActorDependency:
    """Who is acting, with memberships read fresh for this request."""

    async def current_actor(
        user_id: Annotated[str, Depends(current_user_id)], container: ContainerDep
    ) -> Actor:
        return await require_organizations(container).actors.resolve(
            uuid.UUID(hex=user_id)
        )

    return current_actor


def superadmin_dependency(current_actor: ActorDependency) -> ActorDependency:
    """The actor, or 404 for anyone who is not a superadmin: the console stays hidden."""

    async def current_superadmin(
        actor: Annotated[Actor, Depends(current_actor)],
    ) -> Actor:
        if not actor.is_superadmin:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return actor

    return current_superadmin


def require_account(container: Container) -> AccountService:
    if container.account is None:
        raise ServiceNotConfigured(
            "accounts are not configured (set PHARMA_AUTH__OTP_SECRET)"
        )
    return container.account


def request_locale(request: Request) -> Locale:
    return locale_from_accept_language(request.headers.get("accept-language"))


def client_ip(request: Request) -> str | None:
    return request_client_ip(request)


def current_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


RequestLocale = Annotated[Locale, Depends(request_locale)]
ClientIp = Annotated[str | None, Depends(client_ip)]
CurrentSessionToken = Annotated[str | None, Depends(current_session_token)]

__all__ = ["SessionLogin"]
