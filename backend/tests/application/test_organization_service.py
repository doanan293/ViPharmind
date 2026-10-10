import uuid

import pytest

from pharma_agent.application.errors import InvalidInput
from pharma_agent.application.organizations.errors import (
    ForbiddenRole,
    LastOwner,
    MemberNotFound,
    OrganizationNameInvalid,
    OrganizationNotFound,
)
from pharma_agent.application.organizations.service import OrganizationService
from pharma_agent.domain.access.models import Role
from pharma_agent.domain.audit.models import AuditAction
from tests.account_fakes import MutableClock
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


class Fakes:
    def __init__(self) -> None:
        self.organizations = InMemoryOrganizations()
        self.audit = InMemoryAuditLog()
        self.clock = MutableClock()


def build() -> tuple[OrganizationService, Fakes, uuid.UUID]:
    fakes = Fakes()
    service = OrganizationService(
        organizations=fakes.organizations,
        audit=fakes.audit,
        tx=InMemoryTransactions(),
        clock=fakes.clock,
    )
    return service, fakes, uuid.uuid4()


async def test_creator_is_the_first_owner_and_sees_the_org() -> None:
    service, fakes, me = build()
    view = await service.create(actor(me), "  Khoa Dược ")
    assert view.name == "Khoa Dược"
    assert view.role is Role.OWNER and view.member_count == 1
    assert [v.id for v in await service.list_mine(actor(me))] == [view.id]
    assert fakes.audit.actions() == [AuditAction.ORGANIZATION_CREATED]


async def test_names_are_validated() -> None:
    service, _, me = build()
    with pytest.raises(OrganizationNameInvalid):
        await service.create(actor(me), "   ")


async def test_outsiders_get_404_and_members_get_403() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    with pytest.raises(OrganizationNotFound):
        await service.get(actor(uuid.uuid4()), org.id)
    with pytest.raises(OrganizationNotFound):
        await service.get(actor(me), uuid.uuid4())
    member = uuid.uuid4()
    fakes.organizations.seed_member(org.id, member, Role.MEMBER)
    as_member = actor(member, {org.id: Role.MEMBER})
    assert (await service.get(as_member, org.id)).role is Role.MEMBER
    with pytest.raises(ForbiddenRole):
        await service.rename(as_member, org.id, "X")


async def test_superadmin_sees_any_org_without_a_role() -> None:
    service, _, me = build()
    org = await service.create(actor(me), "Org")
    admin = actor(uuid.uuid4(), superadmin=True)
    view = await service.get(admin, org.id)
    assert view.role is None and view.member_count == 1


async def test_owner_changes_roles_and_removes_members() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    owner = actor(me, {org.id: Role.OWNER})
    other = uuid.uuid4()
    fakes.organizations.seed_member(org.id, other, Role.MEMBER)
    await service.set_role(owner, org.id, other, Role.EDITOR)
    assert fakes.organizations.role_of(org.id, other) is Role.EDITOR
    await service.remove_member(owner, org.id, other)
    assert fakes.organizations.role_of(org.id, other) is None
    with pytest.raises(MemberNotFound):
        await service.remove_member(owner, org.id, other)
    assert fakes.audit.actions()[-2:] == [
        AuditAction.MEMBER_ROLE_CHANGED,
        AuditAction.MEMBER_REMOVED,
    ]
    changed = fakes.audit.events[-2]
    assert changed.subject_user_id == other
    assert changed.details == {"from": "member", "to": "editor"}


async def test_the_last_owner_cannot_be_demoted_removed_or_leave() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    owner = actor(me, {org.id: Role.OWNER})
    with pytest.raises(LastOwner):
        await service.set_role(owner, org.id, me, Role.EDITOR)
    with pytest.raises(LastOwner):
        await service.remove_member(owner, org.id, me)
    with pytest.raises(LastOwner):
        await service.leave(owner, org.id)
    fakes.organizations.seed_member(org.id, uuid.uuid4(), Role.OWNER)
    await service.leave(owner, org.id)
    assert fakes.organizations.role_of(org.id, me) is None
    assert fakes.audit.actions()[-1] == AuditAction.MEMBER_LEFT


async def test_outsiders_cannot_leave() -> None:
    service, _, me = build()
    org = await service.create(actor(me), "Org")
    with pytest.raises(OrganizationNotFound):
        await service.leave(actor(uuid.uuid4()), org.id)


async def test_delete_needs_the_exact_name_and_keeps_the_event() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    owner = actor(me, {org.id: Role.OWNER})
    with pytest.raises(InvalidInput):
        await service.delete(owner, org.id, confirm_name="org")
    await service.delete(owner, org.id, confirm_name="Org")
    assert await fakes.organizations.get(org.id) is None
    deleted = fakes.audit.events[-1]
    assert deleted.action is AuditAction.ORGANIZATION_DELETED
    assert deleted.organization_id == org.id and deleted.details == {"name": "Org"}


async def test_a_failed_change_leaves_no_audit_event() -> None:
    service, fakes, me = build()
    org = await service.create(actor(me), "Org")
    fakes.organizations.fail_next = True
    with pytest.raises(RuntimeError):
        await service.rename(actor(me, {org.id: Role.OWNER}), org.id, "New")
    assert fakes.audit.actions() == [AuditAction.ORGANIZATION_CREATED]


async def test_members_are_listed_for_members_only() -> None:
    service, _, me = build()
    org = await service.create(actor(me), "Org")
    members = await service.members(actor(me, {org.id: Role.OWNER}), org.id)
    assert [(m.user_id, m.role) for m in members] == [(me, Role.OWNER)]
    with pytest.raises(OrganizationNotFound):
        await service.members(actor(uuid.uuid4()), org.id)
