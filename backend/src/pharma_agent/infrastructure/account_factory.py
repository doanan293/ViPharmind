"""AccountService over Postgres and the configured email and SMS senders."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.account.service import AccountPolicy, AccountService
from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.auth.passwords import FastapiUsersPasswordHasher
from pharma_agent.infrastructure.notifications.factory import build_email_sender
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.one_time_codes import (
    PostgresOneTimeCodeStore,
)
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.rate_limiter import (
    PostgresRateLimiter,
)
from pharma_agent.infrastructure.persistence.postgres.session_store import (
    PostgresSessionStore,
)
from pharma_agent.infrastructure.settings import Settings


def build_account_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    clock: Clock,
    email: EmailSender | None = None,
    sms: SmsSender | None = None,
) -> AccountService:
    return AccountService(
        accounts=PostgresAccountRepository(sessions),
        codes=PostgresOneTimeCodeStore(sessions),
        limiter=PostgresRateLimiter(sessions, clock),
        email=email if email is not None else build_email_sender(settings.email),
        # The only SMS sender so far; PHARMA_SMS__PROVIDER=none turns phone sign-in off.
        sms=sms if sms is not None else LogSmsSender(),
        hasher=FastapiUsersPasswordHasher(),
        sessions=PostgresSessionStore(
            sessions,
            lifetime_seconds=settings.auth.session_lifetime_seconds,
            clock=clock,
        ),
        clock=clock,
        policy=AccountPolicy(
            otp_secret=settings.auth.require_otp_secret(),
            allowed_sms_regions=frozenset(settings.sms.allowed_country_codes),
            sms_enabled=settings.sms.provider != "none",
            google_enabled=settings.auth.google_enabled,
        ),
        memberships=PostgresOrganizationRepository(sessions),
    )
