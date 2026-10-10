"""Organization, invitation, audit and actor services over Postgres."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.access.service import ActorResolver
from pharma_agent.application.audit.service import AuditService
from pharma_agent.application.organizations.invitations import (
    InvitationPolicy,
    InvitationService,
)
from pharma_agent.application.organizations.service import OrganizationService
from pharma_agent.domain.account.ports import EmailSender
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.notifications.factory import build_email_sender
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.audit_log import PostgresAuditLog
from pharma_agent.infrastructure.persistence.postgres.invitation_repository import (
    PostgresInvitationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.rate_limiter import (
    PostgresRateLimiter,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)
from pharma_agent.infrastructure.settings import Settings


@dataclass(frozen=True)
class OrganizationServices:
    actors: ActorResolver
    organizations: OrganizationService
    invitations: InvitationService
    audit: AuditService


def build_organization_services(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    clock: Clock,
    email: EmailSender | None = None,
) -> OrganizationServices:
    accounts = PostgresAccountRepository(sessions)
    organizations = PostgresOrganizationRepository(sessions)
    audit = PostgresAuditLog(sessions)
    tx = PostgresTransactionFactory(sessions)
    return OrganizationServices(
        actors=ActorResolver(accounts, organizations),
        organizations=OrganizationService(
            organizations=organizations, audit=audit, tx=tx, clock=clock
        ),
        invitations=InvitationService(
            organizations=organizations,
            invitations=PostgresInvitationRepository(sessions),
            accounts=accounts,
            audit=audit,
            tx=tx,
            email=email if email is not None else build_email_sender(settings.email),
            limiter=PostgresRateLimiter(sessions, clock),
            clock=clock,
            policy=InvitationPolicy(frontend_url=settings.auth.frontend_url),
        ),
        audit=AuditService(
            audit=audit, accounts=accounts, organizations=organizations, clock=clock
        ),
    )
