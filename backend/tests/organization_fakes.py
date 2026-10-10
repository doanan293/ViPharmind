"""In-memory organization, invitation and audit ports with transaction semantics.

Writes made inside `InMemoryTransactions.begin()` are queued and applied only when the block
exits without an exception, so tests can prove that a failed change leaves no audit event.
"""

import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime

from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction, AuditEvent
from pharma_agent.domain.audit.ports import Cursor
from pharma_agent.domain.organizations.models import (
    OPEN_STATUSES,
    Invitation,
    Membership,
    MemberView,
    Organization,
)
from pharma_agent.domain.organizations.ports import InvitationConflict
from pharma_agent.domain.shared.transaction import Transaction
from tests.account_fakes import START, InMemoryAccounts


@dataclass
class InMemoryTx:
    pending: list[Callable[[], object]] = field(default_factory=list)

    def later(self, write: Callable[[], object]) -> None:
        self.pending.append(write)


def _tx(tx: Transaction) -> InMemoryTx:
    if not isinstance(tx, InMemoryTx):
        raise TypeError("expected an InMemoryTx")
    return tx


class InMemoryTransactions:
    def __init__(self) -> None:
        self.commits = 0

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[Transaction]:
        tx = InMemoryTx()
        yield tx
        for write in tx.pending:
            write()
        self.commits += 1


class InMemoryOrganizations:
    def __init__(self, accounts: InMemoryAccounts | None = None) -> None:
        self.organizations: dict[uuid.UUID, Organization] = {}
        self.memberships: dict[uuid.UUID, dict[uuid.UUID, Membership]] = {}
        self.accounts = accounts
        self.fail_next = False

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("database unavailable")

    def seed_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, role: Role
    ) -> None:
        self.memberships.setdefault(organization_id, {})[user_id] = Membership(
            organization_id, user_id, role, START
        )

    def role_of(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> Role | None:
        membership = self.memberships.get(organization_id, {}).get(user_id)
        return None if membership is None else membership.role

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        return self.organizations.get(organization_id)

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]:
        return sorted(
            (
                (self.organizations[org_id], members[user_id].role)
                for org_id, members in self.memberships.items()
                if user_id in members and org_id in self.organizations
            ),
            key=lambda pair: (pair[0].name, pair[0].id),
        )

    async def list_all(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[Organization]:
        rows = sorted(
            self.organizations.values(),
            key=lambda o: (o.created_at, o.id),
            reverse=True,
        )
        if cursor is not None:
            at, key = cursor
            rows = [o for o in rows if (o.created_at, o.id) < (at, uuid.UUID(hex=key))]
        return rows[:limit]

    async def member_count(self, organization_id: uuid.UUID) -> int:
        return len(self.memberships.get(organization_id, {}))

    async def create(
        self, organization: Organization, owner_id: uuid.UUID, tx: Transaction
    ) -> None:
        self._maybe_fail()

        def write() -> None:
            self.organizations[organization.id] = organization
            self.seed_member(organization.id, owner_id, Role.OWNER)

        _tx(tx).later(write)

    async def rename(
        self, organization_id: uuid.UUID, name: str, now: datetime, tx: Transaction
    ) -> None:
        self._maybe_fail()
        _tx(tx).later(
            lambda: self.organizations.__setitem__(
                organization_id,
                replace(self.organizations[organization_id], name=name, updated_at=now),
            )
        )

    async def set_quotas(
        self,
        organization_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
        now: datetime,
        tx: Transaction,
    ) -> None:
        self._maybe_fail()
        _tx(tx).later(
            lambda: self.organizations.__setitem__(
                organization_id,
                replace(
                    self.organizations[organization_id],
                    text_quota_bytes=text_quota_bytes,
                    collection_quota=collection_quota,
                    updated_at=now,
                ),
            )
        )

    async def delete(self, organization_id: uuid.UUID, tx: Transaction) -> None:
        self._maybe_fail()

        def write() -> None:
            self.organizations.pop(organization_id, None)
            self.memberships.pop(organization_id, None)

        _tx(tx).later(write)

    async def members(self, organization_id: uuid.UUID) -> list[MemberView]:
        views = []
        for membership in self.memberships.get(organization_id, {}).values():
            user = (
                None
                if self.accounts is None
                else self.accounts.users.get(membership.user_id)
            )
            views.append(
                MemberView(
                    user_id=membership.user_id,
                    display_name="" if user is None else user.display_name,
                    email=None if user is None else user.email,
                    role=membership.role,
                    joined_at=membership.joined_at,
                )
            )
        return views

    async def memberships_of(self, user_id: uuid.UUID) -> dict[uuid.UUID, Role]:
        return {
            org_id: members[user_id].role
            for org_id, members in self.memberships.items()
            if user_id in members
        }

    async def owner_count(self, organization_id: uuid.UUID) -> int:
        return sum(
            m.role is Role.OWNER
            for m in self.memberships.get(organization_id, {}).values()
        )

    async def add_member(self, membership: Membership, tx: Transaction) -> None:
        self._maybe_fail()
        _tx(tx).later(
            lambda: self.memberships.setdefault(
                membership.organization_id, {}
            ).__setitem__(membership.user_id, membership)
        )

    async def set_role(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        tx: Transaction,
    ) -> None:
        self._maybe_fail()
        _tx(tx).later(lambda: self.seed_member(organization_id, user_id, role))

    async def remove_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, tx: Transaction
    ) -> bool:
        self._maybe_fail()
        present = user_id in self.memberships.get(organization_id, {})
        _tx(tx).later(
            lambda: self.memberships.get(organization_id, {}).pop(user_id, None)
        )
        return present


class InMemoryInvitations:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Invitation] = {}

    async def get(self, invitation_id: uuid.UUID) -> Invitation | None:
        return self.rows.get(invitation_id)

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        return next((i for i in self.rows.values() if i.token_hash == token_hash), None)

    async def list_for_organization(
        self, organization_id: uuid.UUID
    ) -> list[Invitation]:
        return sorted(
            (i for i in self.rows.values() if i.organization_id == organization_id),
            key=lambda i: (i.created_at, i.id),
            reverse=True,
        )

    async def open_for(
        self, organization_id: uuid.UUID, email: str
    ) -> Invitation | None:
        return next(
            (
                i
                for i in self.rows.values()
                if i.organization_id == organization_id
                and i.email == email
                and i.status in OPEN_STATUSES
            ),
            None,
        )

    async def create(self, invitation: Invitation, tx: Transaction) -> None:
        if await self.open_for(invitation.organization_id, invitation.email):
            raise InvitationConflict("already open")
        _tx(tx).later(lambda: self.rows.__setitem__(invitation.id, invitation))

    async def update(self, invitation: Invitation, tx: Transaction) -> None:
        _tx(tx).later(lambda: self.rows.__setitem__(invitation.id, invitation))


class InMemoryAuditLog:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def actions(self) -> list[AuditAction]:
        return [event.action for event in self.events]

    async def record(self, event: AuditEvent, tx: Transaction) -> None:
        _tx(tx).later(lambda: self.events.append(event))

    def _page(
        self, events: list[AuditEvent], limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        rows = sorted(events, key=lambda e: (e.occurred_at, e.id), reverse=True)
        if cursor is not None:
            at, key = cursor
            rows = [e for e in rows if (e.occurred_at, e.id) < (at, uuid.UUID(hex=key))]
        return rows[:limit]

    async def for_organization(
        self, organization_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        return self._page(
            [e for e in self.events if e.organization_id == organization_id],
            limit,
            cursor,
        )

    async def for_user(
        self, user_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        return self._page(
            [e for e in self.events if e.subject_user_id == user_id], limit, cursor
        )

    async def all(self, *, limit: int, cursor: Cursor | None) -> list[AuditEvent]:
        return self._page(list(self.events), limit, cursor)


def actor(
    user_id: uuid.UUID,
    memberships: dict[uuid.UUID, Role] | None = None,
    *,
    superadmin: bool = False,
) -> Actor:
    return Actor(user_id, superadmin, memberships or {})
