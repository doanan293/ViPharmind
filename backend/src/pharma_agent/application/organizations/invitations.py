"""Email invitations to an organization (spec §2, §3).

Owners and editors send at once. A member's invitation waits until an owner or editor
approves it; only then is a token made and the email sent. Tokens are stored hashed.
"""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from pydantic import BaseModel

from pharma_agent.application.errors import DeliveryFailed, RateLimited
from pharma_agent.application.mail import Locale
from pharma_agent.application.organizations.errors import (
    AlreadyMember,
    ForbiddenRole,
    InvitationAlreadyOpen,
    InvitationEmailMismatch,
    InvitationExpired,
    InvitationNotFound,
    InvitationNotPending,
    OrganizationNotFound,
)
from pharma_agent.application.organizations.messages import invitation_email
from pharma_agent.application.organizations.service import OrganizationView
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.account.models import normalize_email
from pharma_agent.domain.account.ports import (
    AccountRepository,
    DeliveryError,
    EmailSender,
    RateLimiter,
)
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.organizations.models import (
    INVITATION_TTL,
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
    generate_invitation_token,
    invitation_token_hash,
)
from pharma_agent.domain.organizations.ports import (
    InvitationConflict,
    InvitationRepository,
    OrganizationRepository,
)
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import Transaction, TransactionFactory

HOUR = 3600


@dataclass(frozen=True)
class InvitationPolicy:
    frontend_url: str
    invites_per_inviter_per_hour: int = 20
    invites_per_email_per_hour: int = 5


class InvitationView(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: Role
    status: InvitationStatus
    invited_by: uuid.UUID | None
    invited_by_name: str
    created_at: datetime
    expires_at: datetime | None


class InvitationPreview(BaseModel):
    organization_name: str
    inviter_name: str
    role: Role
    email_hint: str


def email_hint(email: str) -> str:
    """`an@example.com` -> `a**@example.com`: enough to recognise, not to harvest."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}**@{domain}"


class InvitationService:
    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        invitations: InvitationRepository,
        accounts: AccountRepository,
        audit: AuditLog,
        tx: TransactionFactory,
        email: EmailSender,
        limiter: RateLimiter,
        clock: Clock,
        policy: InvitationPolicy,
    ) -> None:
        self._organizations = organizations
        self._invitations = invitations
        self._accounts = accounts
        self._audit = audit
        self._tx = tx
        self._email = email
        self._limiter = limiter
        self._clock = clock
        self._policy = policy

    # Lookups -------------------------------------------------------------------

    async def _organization(
        self, actor: Actor, organization_id: uuid.UUID
    ) -> Organization:
        organization = await self._organizations.get(organization_id)
        if organization is None or not policy.can_view_organization(
            actor, organization_id
        ):
            raise OrganizationNotFound(str(organization_id))
        return organization

    async def _invitation(
        self, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> Invitation:
        invitation = await self._invitations.get(invitation_id)
        if invitation is None or invitation.organization_id != organization_id:
            raise InvitationNotFound(str(invitation_id))
        return invitation

    async def _name_of(self, user_id: uuid.UUID | None) -> str:
        if user_id is None:
            return ""
        user = await self._accounts.get(user_id)
        if user is None:
            return ""
        return user.display_name or user.email or user.phone_number or ""

    async def _view(self, invitation: Invitation) -> InvitationView:
        return InvitationView(
            id=invitation.id,
            organization_id=invitation.organization_id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.effective_status(self._clock.now()),
            invited_by=invitation.invited_by,
            invited_by_name=await self._name_of(invitation.invited_by),
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )

    # Inside the organization ---------------------------------------------------

    async def list(
        self, actor: Actor, organization_id: uuid.UUID
    ) -> list[InvitationView]:
        await self._organization(actor, organization_id)
        rows = await self._invitations.list_for_organization(organization_id)
        if not policy.can_decide_invitation(actor, organization_id):
            rows = [row for row in rows if row.invited_by == actor.user_id]
        return [await self._view(row) for row in rows]

    async def invite(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        email: str,
        role: Role,
        *,
        locale: Locale,
    ) -> InvitationView:
        organization = await self._organization(actor, organization_id)
        if role not in policy.invitable_roles(actor, organization_id):
            raise ForbiddenRole(f"you cannot invite someone as {role.value}")
        address = normalize_email(email)
        existing = await self._accounts.get_by_email(address)
        if existing is not None and organization_id in (
            await self._organizations.memberships_of(existing.id)
        ):
            raise AlreadyMember(f"{address} is already a member")
        if await self._invitations.open_for(organization_id, address) is not None:
            raise InvitationAlreadyOpen(f"an invitation to {address} is already open")
        now = self._clock.now()
        invitation = Invitation(
            id=uuid.uuid4(),
            organization_id=organization_id,
            email=address,
            role=role,
            invited_by=actor.user_id,
            status=InvitationStatus.PENDING_APPROVAL,
            # Replaced with a real token hash when the email is sent.
            token_hash=invitation_token_hash(generate_invitation_token()),
            created_at=now,
            expires_at=None,
            decided_by=None,
            decided_at=None,
        )
        needs_approval = policy.invite_needs_approval(actor, organization_id)
        async with self._tx.begin() as tx:
            try:
                await self._invitations.create(invitation, tx)
            except InvitationConflict as exc:
                raise InvitationAlreadyOpen(str(exc)) from exc
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.INVITATION_CREATED,
                    now,
                    organization_id=organization_id,
                    email=address,
                    role=role.value,
                    needs_approval=needs_approval,
                ),
                tx,
            )
            if not needs_approval:
                invitation = await self._send(
                    tx, actor, organization, invitation, locale
                )
        return await self._view(invitation)

    async def _send(
        self,
        tx: Transaction,
        actor: Actor,
        organization: Organization,
        invitation: Invitation,
        locale: Locale,
    ) -> Invitation:
        """Issue a fresh token, store its hash and send the email inside `tx`.

        A delivery failure raises, so the transaction rolls back and nothing is marked sent.
        """
        await self._limit(actor.user_id, invitation.email)
        token = generate_invitation_token()
        now = self._clock.now()
        sent = replace(
            invitation,
            status=InvitationStatus.SENT,
            token_hash=invitation_token_hash(token),
            expires_at=now + INVITATION_TTL,
        )
        if not await self._invitations.update(sent, tx, expected=invitation.status):
            raise InvitationNotPending("the invitation changed meanwhile")
        link = f"{self._policy.frontend_url.rstrip('/')}/invitations/{token}"
        content = invitation_email(
            organization=organization.name,
            inviter=await self._name_of(actor.user_id),
            role=invitation.role,
            link=link,
            locale=locale,
        )
        try:
            await self._email.send(
                to=invitation.email,
                subject=content.subject,
                text=content.text,
                html=content.html,
            )
        except DeliveryError as exc:
            raise DeliveryFailed("the invitation could not be sent, try again") from exc
        return sent

    async def _limit(self, inviter: uuid.UUID, email: str) -> None:
        limits = [
            (f"invite-by:{inviter}", self._policy.invites_per_inviter_per_hour),
            (f"invite-to:{email}", self._policy.invites_per_email_per_hour),
        ]
        taken: list[str] = []
        for key, limit in limits:
            retry_after = await self._limiter.acquire(
                key, limit=limit, window_seconds=HOUR
            )
            if retry_after is not None:
                for done in taken:
                    await self._limiter.release(done, window_seconds=HOUR)
                raise RateLimited(retry_after)
            taken.append(key)

    async def _decide(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        *,
        expected: frozenset[InvitationStatus],
    ) -> tuple[Organization, Invitation]:
        organization = await self._organization(actor, organization_id)
        invitation = await self._invitation(organization_id, invitation_id)
        if invitation.effective_status(self._clock.now()) not in expected:
            raise InvitationNotPending("the invitation is no longer open")
        return organization, invitation

    async def approve(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        *,
        locale: Locale,
    ) -> InvitationView:
        organization, invitation = await self._decide(
            actor,
            organization_id,
            invitation_id,
            expected=frozenset({InvitationStatus.PENDING_APPROVAL}),
        )
        if not policy.can_decide_invitation(actor, organization_id):
            raise ForbiddenRole("only owners and editors approve invitations")
        now = self._clock.now()
        decided = replace(invitation, decided_by=actor.user_id, decided_at=now)
        async with self._tx.begin() as tx:
            sent = await self._send(tx, actor, organization, decided, locale)
            await self._record(tx, actor, AuditAction.INVITATION_APPROVED, invitation)
        return await self._view(sent)

    async def reject(
        self, actor: Actor, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationView:
        _, invitation = await self._decide(
            actor,
            organization_id,
            invitation_id,
            expected=frozenset({InvitationStatus.PENDING_APPROVAL}),
        )
        if not policy.can_decide_invitation(actor, organization_id):
            raise ForbiddenRole("only owners and editors reject invitations")
        return await self._close(
            actor,
            invitation,
            InvitationStatus.REJECTED,
            AuditAction.INVITATION_REJECTED,
        )

    async def revoke(
        self, actor: Actor, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationView:
        _, invitation = await self._decide(
            actor,
            organization_id,
            invitation_id,
            expected=frozenset(
                {InvitationStatus.PENDING_APPROVAL, InvitationStatus.SENT}
            ),
        )
        if not policy.can_cancel_invitation(
            actor, organization_id, invited_by=invitation.invited_by
        ):
            raise ForbiddenRole("you cannot revoke this invitation")
        return await self._close(
            actor, invitation, InvitationStatus.REVOKED, AuditAction.INVITATION_REVOKED
        )

    async def resend(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
        *,
        locale: Locale,
    ) -> InvitationView:
        """Send again with a new token and a new deadline; the old link stops working."""
        organization, invitation = await self._decide(
            actor,
            organization_id,
            invitation_id,
            expected=frozenset({InvitationStatus.SENT, InvitationStatus.EXPIRED}),
        )
        if not policy.can_cancel_invitation(
            actor, organization_id, invited_by=invitation.invited_by
        ):
            raise ForbiddenRole("you cannot resend this invitation")
        async with self._tx.begin() as tx:
            sent = await self._send(tx, actor, organization, invitation, locale)
            await self._record(tx, actor, AuditAction.INVITATION_RESENT, invitation)
        return await self._view(sent)

    async def _close(
        self,
        actor: Actor,
        invitation: Invitation,
        status: InvitationStatus,
        action: AuditAction,
    ) -> InvitationView:
        closed = replace(
            invitation,
            status=status,
            decided_by=actor.user_id,
            decided_at=self._clock.now(),
        )
        async with self._tx.begin() as tx:
            if not await self._invitations.update(
                closed, tx, expected=invitation.status
            ):
                raise InvitationNotPending("the invitation changed meanwhile")
            await self._record(tx, actor, action, invitation)
        return await self._view(closed)

    async def _record(
        self,
        tx: Transaction,
        actor: Actor,
        action: AuditAction,
        invitation: Invitation,
    ) -> None:
        await self._audit.record(
            new_event(
                actor,
                action,
                self._clock.now(),
                organization_id=invitation.organization_id,
                email=invitation.email,
                role=invitation.role.value,
            ),
            tx,
        )

    # The invited person -----------------------------------------------------------

    async def _open_by_token(self, token: str) -> Invitation:
        invitation = await self._invitations.get_by_token_hash(
            invitation_token_hash(token)
        )
        if invitation is None:
            raise InvitationNotFound("the invitation does not exist")
        status = invitation.effective_status(self._clock.now())
        if status is InvitationStatus.EXPIRED:
            raise InvitationExpired("the invitation has expired")
        if status is not InvitationStatus.SENT:
            raise InvitationNotPending("the invitation is no longer open")
        return invitation

    async def preview(self, token: str) -> InvitationPreview:
        """Public: anyone holding the link sees whom it invites, nothing more."""
        try:
            invitation = await self._open_by_token(token)
        except (InvitationExpired, InvitationNotPending) as exc:
            raise InvitationNotFound("the invitation is no longer valid") from exc
        organization = await self._organizations.get(invitation.organization_id)
        if organization is None:
            raise InvitationNotFound("the invitation is no longer valid")
        return InvitationPreview(
            organization_name=organization.name,
            inviter_name=await self._name_of(invitation.invited_by),
            role=invitation.role,
            email_hint=email_hint(invitation.email),
        )

    async def _invitee(self, actor: Actor, invitation: Invitation) -> None:
        user = await self._accounts.get(actor.user_id)
        if user is None or not user.email_verified or user.email != invitation.email:
            raise InvitationEmailMismatch(
                f"this invitation is for {email_hint(invitation.email)}"
            )

    async def accept(self, actor: Actor, token: str) -> OrganizationView:
        invitation = await self._open_by_token(token)
        await self._invitee(actor, invitation)
        organization = await self._organizations.get(invitation.organization_id)
        if organization is None:
            raise InvitationNotFound("the organization no longer exists")
        now = self._clock.now()
        member = Actor(
            actor.user_id,
            actor.is_superadmin,
            {**actor.memberships, organization.id: invitation.role},
        )
        already = actor.role_in(organization.id) is not None
        accepted = replace(
            invitation,
            status=InvitationStatus.ACCEPTED,
            decided_by=actor.user_id,
            decided_at=now,
        )
        async with self._tx.begin() as tx:
            # Compare-and-set: a revoke or a second accept running at the same time loses.
            if not await self._invitations.update(
                accepted, tx, expected=invitation.status
            ):
                raise InvitationNotPending("the invitation changed meanwhile")
            if not already:
                await self._organizations.add_member(
                    Membership(organization.id, actor.user_id, invitation.role, now), tx
                )
                await self._audit.record(
                    new_event(
                        member,
                        AuditAction.MEMBER_JOINED,
                        now,
                        organization_id=organization.id,
                        subject_user_id=actor.user_id,
                        role=invitation.role.value,
                        via="invitation",
                    ),
                    tx,
                )
        role = actor.role_in(organization.id) or invitation.role
        return OrganizationView(
            id=organization.id,
            name=organization.name,
            role=role,
            member_count=await self._organizations.member_count(organization.id),
            created_at=organization.created_at,
        )

    async def decline(self, actor: Actor, token: str) -> None:
        invitation = await self._open_by_token(token)
        await self._invitee(actor, invitation)
        closed = replace(
            invitation,
            status=InvitationStatus.DECLINED,
            decided_by=actor.user_id,
            decided_at=self._clock.now(),
        )
        async with self._tx.begin() as tx:
            if not await self._invitations.update(
                closed, tx, expected=invitation.status
            ):
                raise InvitationNotPending("the invitation changed meanwhile")
            await self._record(tx, actor, AuditAction.INVITATION_DECLINED, invitation)
