from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.account.messages import (
    Locale,
    locale_from_accept_language,
)
from pharma_agent.application.account.service import AccountService
from pharma_agent.application.chat.service import ChatService
from pharma_agent.application.errors import (
    AgentUnavailable,
    ServiceNotConfigured,
    ServiceStarting,
)
from pharma_agent.application.feedback.service import FeedbackService
from pharma_agent.infrastructure.auth.users import (
    SESSION_COOKIE_NAME,
    Auth,
    SessionLogin,
)
from pharma_agent.infrastructure.container import Container
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


def require_account(container: Container) -> AccountService:
    if container.account is None:
        raise ServiceNotConfigured(
            "accounts are not configured (set PHARMA_AUTH__OTP_SECRET)"
        )
    return container.account


def request_locale(request: Request) -> Locale:
    return locale_from_accept_language(request.headers.get("accept-language"))


def client_ip(request: Request) -> str | None:
    return None if request.client is None else request.client.host


def current_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


RequestLocale = Annotated[Locale, Depends(request_locale)]
ClientIp = Annotated[str | None, Depends(client_ip)]
CurrentSessionToken = Annotated[str | None, Depends(current_session_token)]

__all__ = ["SessionLogin"]
