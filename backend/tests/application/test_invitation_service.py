import re
import uuid
from dataclasses import replace

import pytest

from pharma_agent.application.errors import RateLimited
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
from pharma_agent.application.organizations.invitations import (
    InvitationPolicy,
    InvitationService,
)
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction
from pharma_agent.domain.organizations.models import InvitationStatus, Organization
from tests.account_fakes import (
    START,
    InMemoryAccounts,
    InMemoryLimiter,
    MutableClock,
    RecordingEmailSender,
)
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryInvitations,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)

TOKEN = re.compile(r"/invitations/([A-Za-z0-9_-]+)")


class Fakes:
    def __init__(self) -> None:
        self.clock = MutableClock()
        self.accounts = InMemoryAccounts()
        self.organizations = InMemoryOrganizations(self.accounts)
        self.invitations = InMemoryInvitations()
        self.audit = InMemoryAuditLog()
        self.email = RecordingEmailSender()

    def last_token(self, to: str) -> str:
        sent = [mail for mail in self.email.sent if mail.to == to]
        match = TOKEN.search(sent[-1].text)
        assert match is not None
        return match.group(1)


async def build() -> tuple[InvitationService, Fakes, Organization, uuid.UUID]:
    fakes = Fakes()
    owner = fakes.accounts.add(email="owner@example.com", email_verified=True)
    org = Organization(uuid.uuid4(), "Khoa Dược", None, None, START, START)
    fakes.organizations.organizations[org.id] = org
    fakes.organizations.seed_member(org.id, owner.id, Role.OWNER)
    service = InvitationService(
        organizations=fakes.organizations,
        invitations=fakes.invitations,
        accounts=fakes.accounts,
        audit=fakes.audit,
        tx=InMemoryTransactions(),
        email=fakes.email,
        limiter=InMemoryLimiter(fakes.clock),
        clock=fakes.clock,
        policy=InvitationPolicy(frontend_url="https://app.example"),
    )
    return service, fakes, org, owner.id


def as_role(user_id: uuid.UUID, org: Organization, role: Role) -> Actor:
    return actor(user_id, {org.id: role})


def member(fakes: Fakes, org: Organization, role: Role, email: str) -> Actor:
    user = fakes.accounts.add(email=email, email_verified=True)
    fakes.organizations.seed_member(org.id, user.id, role)
    return as_role(user.id, org, role)


async def test_owner_invite_sends_a_link_and_accepting_joins() -> None:
    s, f, org, owner = await build()
    view = await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        " New@Example.com ",
        Role.EDITOR,
        locale="vi",
    )
    assert view.status is InvitationStatus.SENT and view.email == "new@example.com"
    token = f.last_token("new@example.com")
    assert "https://app.example/invitations/" in f.email.sent[-1].text

    preview = await s.preview(token)
    assert preview.organization_name == "Khoa Dược"
    assert preview.role is Role.EDITOR and preview.email_hint == "n**@example.com"

    invitee = f.accounts.add(email="new@example.com", email_verified=True)
    joined = await s.accept(actor(invitee.id), token)
    assert joined.role is Role.EDITOR and joined.id == org.id
    assert f.organizations.role_of(org.id, invitee.id) is Role.EDITOR
    assert f.audit.actions()[-1] is AuditAction.MEMBER_JOINED
    with pytest.raises(InvitationNotPending):
        await s.accept(actor(invitee.id), token)


async def test_member_invites_wait_for_approval() -> None:
    s, f, org, _ = await build()
    me = member(f, org, Role.MEMBER, "m@example.com")
    view = await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")
    assert view.status is InvitationStatus.PENDING_APPROVAL
    assert all(mail.to != "x@example.com" for mail in f.email.sent)
    with pytest.raises(ForbiddenRole):
        await s.approve(me, org.id, view.id, locale="vi")
    editor = member(f, org, Role.EDITOR, "e@example.com")
    approved = await s.approve(editor, org.id, view.id, locale="en")
    assert approved.status is InvitationStatus.SENT
    assert f.email.sent[-1].to == "x@example.com"
    assert AuditAction.INVITATION_APPROVED in f.audit.actions()


async def test_rejecting_a_pending_invitation() -> None:
    s, f, org, owner = await build()
    me = member(f, org, Role.MEMBER, "m@example.com")
    view = await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")
    rejected = await s.reject(as_role(owner, org, Role.OWNER), org.id, view.id)
    assert rejected.status is InvitationStatus.REJECTED
    with pytest.raises(InvitationNotPending):
        await s.approve(as_role(owner, org, Role.OWNER), org.id, view.id, locale="vi")


async def test_roles_limit_what_can_be_granted() -> None:
    s, f, org, _ = await build()
    editor = member(f, org, Role.EDITOR, "e@example.com")
    with pytest.raises(ForbiddenRole):
        await s.invite(editor, org.id, "x@example.com", Role.OWNER, locale="vi")
    me = member(f, org, Role.MEMBER, "m@example.com")
    with pytest.raises(ForbiddenRole):
        await s.invite(me, org.id, "x@example.com", Role.EDITOR, locale="vi")
    with pytest.raises(OrganizationNotFound):
        await s.invite(
            actor(uuid.uuid4()), org.id, "x@example.com", Role.MEMBER, locale="vi"
        )


async def test_existing_members_and_open_invitations_are_refused() -> None:
    s, _, org, owner = await build()
    me = as_role(owner, org, Role.OWNER)
    with pytest.raises(AlreadyMember):
        await s.invite(me, org.id, "OWNER@example.com", Role.MEMBER, locale="vi")
    await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")
    with pytest.raises(InvitationAlreadyOpen):
        await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")


async def test_accepting_needs_the_invited_verified_email() -> None:
    s, f, org, owner = await build()
    await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        "x@example.com",
        Role.MEMBER,
        locale="vi",
    )
    token = f.last_token("x@example.com")
    other = f.accounts.add(email="y@example.com", email_verified=True)
    with pytest.raises(InvitationEmailMismatch):
        await s.accept(actor(other.id), token)
    unverified = f.accounts.add(email="x@example.com", email_verified=False)
    with pytest.raises(InvitationEmailMismatch):
        await s.accept(actor(unverified.id), token)


async def test_invitations_expire_after_seven_days() -> None:
    s, f, org, owner = await build()
    await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        "x@example.com",
        Role.MEMBER,
        locale="vi",
    )
    token = f.last_token("x@example.com")
    f.clock.advance(days=7)
    invitee = f.accounts.add(email="x@example.com", email_verified=True)
    with pytest.raises(InvitationExpired):
        await s.accept(actor(invitee.id), token)
    with pytest.raises(InvitationNotFound):
        await s.preview(token)


async def test_an_invitation_survives_its_inviter_leaving() -> None:
    s, f, org, _ = await build()
    editor = member(f, org, Role.EDITOR, "e@example.com")
    await s.invite(editor, org.id, "x@example.com", Role.MEMBER, locale="vi")
    token = f.last_token("x@example.com")
    del f.organizations.memberships[org.id][editor.user_id]
    invitee = f.accounts.add(email="x@example.com", email_verified=True)
    joined = await s.accept(actor(invitee.id), token)
    assert joined.role is Role.MEMBER


async def test_resend_replaces_the_token_and_revoke_closes_it() -> None:
    s, f, org, owner = await build()
    me = as_role(owner, org, Role.OWNER)
    view = await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")
    old = f.last_token("x@example.com")
    f.clock.advance(seconds=61)
    await s.resend(me, org.id, view.id, locale="vi")
    new = f.last_token("x@example.com")
    assert new != old
    with pytest.raises(InvitationNotFound):
        await s.preview(old)
    revoked = await s.revoke(me, org.id, view.id)
    assert revoked.status is InvitationStatus.REVOKED
    with pytest.raises(InvitationNotFound):
        await s.preview(new)


async def test_declining_closes_the_invitation() -> None:
    s, f, org, owner = await build()
    view = await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        "x@example.com",
        Role.MEMBER,
        locale="vi",
    )
    token = f.last_token("x@example.com")
    invitee = f.accounts.add(email="x@example.com", email_verified=True)
    await s.decline(actor(invitee.id), token)
    stored = await f.invitations.get(view.id)
    assert stored is not None and stored.status is InvitationStatus.DECLINED


async def test_members_see_only_their_own_invitations() -> None:
    s, f, org, owner = await build()
    me = member(f, org, Role.MEMBER, "m@example.com")
    await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        "a@example.com",
        Role.MEMBER,
        locale="vi",
    )
    await s.invite(me, org.id, "b@example.com", Role.MEMBER, locale="vi")
    assert [i.email for i in await s.list(me, org.id)] == ["b@example.com"]
    owner_view = await s.list(as_role(owner, org, Role.OWNER), org.id)
    assert {i.email for i in owner_view} == {"a@example.com", "b@example.com"}


async def test_sending_to_one_address_is_rate_limited() -> None:
    s, f, org, owner = await build()
    me = as_role(owner, org, Role.OWNER)
    view = await s.invite(me, org.id, "x@example.com", Role.MEMBER, locale="vi")
    for _ in range(4):
        f.clock.advance(minutes=1)
        await s.resend(me, org.id, view.id, locale="vi")
    f.clock.advance(minutes=1)
    with pytest.raises(RateLimited):
        await s.resend(me, org.id, view.id, locale="vi")
    f.clock.advance(hours=1)
    await s.resend(me, org.id, view.id, locale="vi")


async def test_an_invitation_revoked_while_being_accepted_grants_nothing() -> None:
    s, f, org, owner = await build()
    await s.invite(
        as_role(owner, org, Role.OWNER),
        org.id,
        "new@example.com",
        Role.MEMBER,
        locale="vi",
    )
    token = f.last_token("new@example.com")
    invitee = f.accounts.add(email="new@example.com", email_verified=True)
    stored = next(iter(f.invitations.rows.values()))
    # The owner revokes after the accept read the invitation, before it wrote.
    original_get = f.invitations.get_by_token_hash

    async def stale_read(token_hash: str):
        found = await original_get(token_hash)
        f.invitations.rows[stored.id] = replace(stored, status=InvitationStatus.REVOKED)
        return found

    f.invitations.get_by_token_hash = stale_read
    with pytest.raises(InvitationNotPending):
        await s.accept(actor(invitee.id), token)
    assert f.organizations.role_of(org.id, invitee.id) is None
