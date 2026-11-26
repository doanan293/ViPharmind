import uuid
from datetime import timedelta

import pytest

from pharma_agent.application.audit.service import AuditService
from pharma_agent.application.organizations.errors import (
    ForbiddenRole,
    OrganizationNotFound,
)
from pharma_agent.domain.access.models import Role
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.organizations.models import Organization
from tests.account_fakes import START, InMemoryAccounts, MutableClock
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


async def build() -> tuple[AuditService, InMemoryAuditLog, Organization, uuid.UUID]:
    accounts = InMemoryAccounts()
    organizations = InMemoryOrganizations(accounts)
    audit = InMemoryAuditLog()
    owner = accounts.add(email="owner@example.com")
    org = Organization(uuid.uuid4(), "Org", None, None, START, START)
    organizations.organizations[org.id] = org
    organizations.seed_member(org.id, owner.id, Role.OWNER)
    tx = InMemoryTransactions()
    me = actor(owner.id, {org.id: Role.OWNER})
    for minute in range(5):
        async with tx.begin() as t:
            await audit.record(
                new_event(
                    me,
                    AuditAction.ORGANIZATION_RENAMED,
                    START + timedelta(minutes=minute),
                    organization_id=org.id,
                    n=minute,
                ),
                t,
            )
    async with tx.begin() as t:
        await audit.record(
            new_event(me, AuditAction.USER_ENABLED, START, subject_user_id=owner.id), t
        )
    service = AuditService(
        audit=audit,
        accounts=accounts,
        organizations=organizations,
        clock=MutableClock(),
    )
    return service, audit, org, owner.id


async def test_organization_log_pages_newest_first_with_actor_names() -> None:
    service, _, org, owner = await build()
    me = actor(owner, {org.id: Role.OWNER})
    first = await service.for_organization(me, org.id, limit=3, cursor=None)
    assert [item.details["n"] for item in first.items] == [4, 3, 2]
    assert first.items[0].actor_name == "owner@example.com"
    assert first.next_cursor is not None
    rest = await service.for_organization(me, org.id, limit=3, cursor=first.next_cursor)
    assert [item.details["n"] for item in rest.items] == [1, 0]
    assert rest.next_cursor is None


async def test_members_and_outsiders_cannot_read_the_organization_log() -> None:
    service, _, org, _ = await build()
    with pytest.raises(ForbiddenRole):
        await service.for_organization(
            actor(uuid.uuid4(), {org.id: Role.MEMBER}), org.id, limit=10, cursor=None
        )
    with pytest.raises(OrganizationNotFound):
        await service.for_organization(
            actor(uuid.uuid4()), org.id, limit=10, cursor=None
        )


async def test_mine_lists_events_about_me_and_everything_is_superadmin_only() -> None:
    service, _, _, owner = await build()
    mine = await service.mine(actor(owner), limit=10, cursor=None)
    assert [item.action for item in mine.items] == [AuditAction.USER_ENABLED]
    with pytest.raises(ForbiddenRole):
        await service.everything(actor(owner), limit=10, cursor=None)
    everything = await service.everything(
        actor(uuid.uuid4(), superadmin=True), limit=10, cursor=None
    )
    assert len(everything.items) == 6


async def test_events_about_a_member_carry_the_member_name() -> None:
    accounts = InMemoryAccounts()
    organizations = InMemoryOrganizations(accounts)
    audit = InMemoryAuditLog()
    owner = accounts.add(email="owner@example.com")
    member = accounts.add(email="loi@example.com")
    org = Organization(uuid.uuid4(), "Org", None, None, START, START)
    organizations.organizations[org.id] = org
    organizations.seed_member(org.id, owner.id, Role.OWNER)
    me = actor(owner.id, {org.id: Role.OWNER})
    async with InMemoryTransactions().begin() as t:
        await audit.record(
            new_event(
                me,
                AuditAction.MEMBER_ROLE_CHANGED,
                START,
                organization_id=org.id,
                subject_user_id=member.id,
            ),
            t,
        )
        await audit.record(
            new_event(
                me,
                AuditAction.MEMBER_REMOVED,
                START + timedelta(minutes=1),
                organization_id=org.id,
                subject_user_id=uuid.uuid4(),  # an account deleted since
            ),
            t,
        )
    service = AuditService(
        audit=audit,
        accounts=accounts,
        organizations=organizations,
        clock=MutableClock(),
    )
    page = await service.for_organization(me, org.id, limit=10, cursor=None)
    names = {item.action: item.subject_name for item in page.items}
    assert names[AuditAction.MEMBER_ROLE_CHANGED] == "loi@example.com"
    assert names[AuditAction.MEMBER_REMOVED] == ""
