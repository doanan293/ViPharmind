import uuid
from dataclasses import replace
from datetime import timedelta

import pytest

from pharma_agent.application.admin.service import AdminService
from pharma_agent.application.errors import ForbiddenRole, InvalidInput
from pharma_agent.domain.audit.models import AuditAction
from pharma_agent.domain.organizations.models import Organization
from tests.account_fakes import (
    START,
    InMemoryAccounts,
    InMemorySessions,
    MutableClock,
)
from tests.organization_fakes import (
    InMemoryAccountAdmin,
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


class World:
    def __init__(self) -> None:
        self.accounts = InMemoryAccounts()
        self.admin_store = InMemoryAccountAdmin(self.accounts)
        self.organizations = InMemoryOrganizations(self.accounts)
        self.sessions = InMemorySessions()
        self.audit = InMemoryAuditLog()
        self.service = AdminService(
            accounts=self.admin_store,
            organizations=self.organizations,
            sessions=self.sessions,
            audit=self.audit,
            tx=InMemoryTransactions(),
            clock=MutableClock(),
        )
        self.admin = actor(uuid.uuid4(), superadmin=True)


async def test_only_superadmins_use_the_console() -> None:
    w = World()
    with pytest.raises(ForbiddenRole):
        await w.service.users(actor(uuid.uuid4()), query=None, limit=10, cursor=None)


async def test_users_are_searched_and_paged_newest_first() -> None:
    w = World()
    for n in range(3):
        user = w.accounts.add(email=f"user{n}@example.com")
        w.accounts.users[user.id] = replace(
            user, created_at=START + timedelta(minutes=n)
        )
    first = await w.service.users(w.admin, query=None, limit=2, cursor=None)
    assert [u.email for u in first.items] == ["user2@example.com", "user1@example.com"]
    rest = await w.service.users(w.admin, query=None, limit=2, cursor=first.next_cursor)
    assert [u.email for u in rest.items] == ["user0@example.com"]
    found = await w.service.users(w.admin, query="USER1", limit=10, cursor=None)
    assert [u.email for u in found.items] == ["user1@example.com"]


async def test_disabling_ends_every_session_and_is_audited() -> None:
    w = World()
    user = w.accounts.add(email="an@example.com")
    w.sessions.add(user.id, "t1")
    view = await w.service.set_user_active(w.admin, user.id, active=False)
    assert view.is_active is False
    assert await w.sessions.for_user(user.id) == []
    event = w.audit.events[-1]
    assert event.action is AuditAction.USER_DISABLED
    assert event.subject_user_id == user.id and event.actor_was_superadmin
    enabled = await w.service.set_user_active(w.admin, user.id, active=True)
    assert enabled.is_active and w.audit.actions()[-1] is AuditAction.USER_ENABLED


async def test_superadmins_cannot_lock_themselves_out() -> None:
    w = World()
    me = w.accounts.add(email="admin@example.com")
    with pytest.raises(InvalidInput):
        await w.service.set_user_active(
            actor(me.id, superadmin=True), me.id, active=False
        )


async def test_quotas_are_set_per_user_and_organization() -> None:
    w = World()
    user = w.accounts.add(email="an@example.com")
    view = await w.service.set_user_quotas(
        w.admin, user.id, text_quota_bytes=5_000_000, collection_quota=None
    )
    assert (view.text_quota_bytes, view.collection_quota) == (5_000_000, None)
    org = Organization(uuid.uuid4(), "Org", None, None, START, START)
    w.organizations.organizations[org.id] = org
    updated = await w.service.set_organization_quotas(
        w.admin, org.id, text_quota_bytes=None, collection_quota=50
    )
    assert updated.collection_quota == 50
    page = await w.service.organizations(w.admin, limit=10, cursor=None)
    assert [o.id for o in page.items] == [org.id]
    assert [e.action for e in w.audit.events] == [AuditAction.QUOTA_CHANGED] * 2
