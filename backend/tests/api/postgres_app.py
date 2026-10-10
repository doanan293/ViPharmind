"""The real app over a migrated Postgres database with only the services auth tests need."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
from sqlalchemy import text

from pharma_agent.api.app import create_app
from pharma_agent.application.conversation.service import ConversationService
from pharma_agent.domain.shared.clock import SystemClock
from pharma_agent.infrastructure.account_factory import build_account_service
from pharma_agent.infrastructure.container import Container
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.settings import Settings
from tests.account_fakes import RecordingEmailSender, RecordingSmsSender
from tests.api.asgi import running
from tests.memory_repository import (
    InMemoryCitationReader,
    InMemoryConversationRepository,
    InMemoryFeedbackRepository,
)

JWT_SECRET = "s" * 40
CSRF_SECRET = "c" * 40
OTP_SECRET = "o" * 40
PASSWORD = "S3cure-password!"


@dataclass
class AppOutbox:
    """What the app under test would have emailed or texted."""

    email: RecordingEmailSender = field(default_factory=RecordingEmailSender)
    sms: RecordingSmsSender = field(default_factory=RecordingSmsSender)


@asynccontextmanager
async def postgres_app(
    dsn: str,
    *,
    auth: dict[str, object] | None = None,
    api: dict[str, object] | None = None,
) -> AsyncGenerator[tuple[httpx.AsyncClient, Database, AppOutbox]]:
    database = Database(dsn, pool_size=2)
    outbox = AppOutbox()
    # Every test client shares one fake IP and the database lives for the whole session,
    # so counters from earlier tests would trip the per-IP limits.
    async with database.engine.begin() as connection:
        await connection.execute(text("TRUNCATE rate_limit_buckets, one_time_codes"))
    settings = Settings(
        _env_file=None,
        auth={
            "jwt_secret": JWT_SECRET,
            "csrf_secret": CSRF_SECRET,
            "otp_secret": OTP_SECRET,
            **(auth or {}),
        },
        postgres={"dsn": dsn},
        api=api or {},
    )

    @asynccontextmanager
    async def factory(resolved: Settings) -> AsyncGenerator[Container]:
        yield Container(
            sessions=database.sessions,
            conversations=ConversationService(
                InMemoryConversationRepository(),
                SystemClock(),
                feedback=InMemoryFeedbackRepository(),
                citations=InMemoryCitationReader(),
            ),
            account=build_account_service(
                resolved,
                database.sessions,
                clock=SystemClock(),
                email=outbox.email,
                sms=outbox.sms,
            ),
            health_checks={"postgres": database.ping},
        )

    try:
        async with running(create_app(settings, container_factory=factory)) as client:
            yield client, database, outbox
    finally:
        await database.dispose()


def new_email() -> str:
    return f"{uuid4().hex[:12]}@example.com"


async def register(client: httpx.AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text


async def cookie_login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    response = await client.post(
        "/api/v1/auth/cookie/login", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 204, response.text
    return response


def csrf_header(client: httpx.AsyncClient) -> dict[str, str]:
    return {"x-csrftoken": client.cookies["csrftoken"]}


def set_cookie(response: httpx.Response, name: str) -> str:
    """The lower-cased Set-Cookie header for `name` (a response may set several cookies)."""
    return next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{name}=")
    ).lower()


async def verified_register(
    client: httpx.AsyncClient, outbox: AppOutbox, email: str
) -> None:
    """Register, then verify the email with the code the app sent; this signs the user in."""
    await register(client, email)
    code = outbox.email.last_code(email)
    response = await client.post(
        "/api/v1/auth/email/verify", json={"email": email, "code": code}
    )
    assert response.status_code == 204, response.text
