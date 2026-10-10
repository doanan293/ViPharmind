import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, text

from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.organizations.models import (
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
)
from pharma_agent.domain.organizations.ports import InvitationConflict
from pharma_agent.infrastructure.persistence.postgres.audit_log import PostgresAuditLog
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.invitation_repository import (
    PostgresInvitationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.tables import UserTable
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


@pytest.fixture
async def database(migrated_dsn: str) -> AsyncIterator[Database]:
    db = Database(migrated_dsn, pool_size=2)
    async with db.engine.begin() as connection:
        await connection.execute(
            text('TRUNCATE "user", organizations, audit_events CASCADE')
        )
    yield db
    await db.dispose()


async def add_user(db: Database, name: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(UserTable).values(
                id=user_id,
                email=f"{name}-{user_id.hex[:6]}@example.com",
                hashed_password="hash",
                is_active=True,
                is_superuser=False,
                is_verified=True,
                display_name=name,
            )
        )
    return user_id


def organization(name: str = "Khoa Dược") -> Organization:
    return Organization(uuid.uuid4(), name, None, None, NOW, NOW)


def invitation(org: uuid.UUID, by: uuid.UUID, email: str) -> Invitation:
    return Invitation(
        id=uuid.uuid4(),
        organization_id=org,
        email=email,
        role=Role.MEMBER,
        invited_by=by,
        status=InvitationStatus.SENT,
        token_hash=uuid.uuid4().hex,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
        decided_by=None,
        decided_at=None,
    )


async def test_members_roles_and_cascade(database: Database) -> None:
    repo = PostgresOrganizationRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    owner, member = await add_user(database, "An"), await add_user(database, "Bình")
    org = organization()
    async with tx.begin() as t:
        await repo.create(org, owner, t)
    async with tx.begin() as t:
        await repo.add_member(Membership(org.id, member, Role.MEMBER, NOW), t)

    assert await repo.get(org.id) == org
    assert await repo.owner_count(org.id) == 1
    assert await repo.member_count(org.id) == 2
    assert await repo.memberships_of(member) == {org.id: Role.MEMBER}
    assert await repo.list_for_user(owner) == [(org, Role.OWNER)]
    members = {m.user_id: m for m in await repo.members(org.id)}
    assert members[owner].display_name == "An" and members[owner].role is Role.OWNER

    async with tx.begin() as t:
        await repo.set_role(org.id, member, Role.EDITOR, t)
        await repo.rename(org.id, "Khoa Dược lâm sàng", NOW, t)
    assert (await repo.memberships_of(member))[org.id] is Role.EDITOR
    page = await repo.list_all(limit=10, cursor=None)
    assert [o.name for o in page] == ["Khoa Dược lâm sàng"]

    async with tx.begin() as t:
        assert await repo.remove_member(org.id, member, t)
        assert not await repo.remove_member(org.id, member, t)
    async with tx.begin() as t:
        await repo.delete(org.id, t)
    assert await repo.get(org.id) is None
    assert await repo.memberships_of(owner) == {}


async def test_one_open_invitation_per_email(database: Database) -> None:
    orgs = PostgresOrganizationRepository(database.sessions)
    invitations = PostgresInvitationRepository(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    owner = await add_user(database, "An")
    org = organization()
    async with tx.begin() as t:
        await orgs.create(org, owner, t)
    first = invitation(org.id, owner, "new@example.com")
    async with tx.begin() as t:
        await invitations.create(first, t)
    with pytest.raises(InvitationConflict):
        async with tx.begin() as t:
            await invitations.create(invitation(org.id, owner, "new@example.com"), t)

    assert await invitations.open_for(org.id, "new@example.com") == first
    assert await invitations.get_by_token_hash(first.token_hash) == first
    declined = replace(first, status=InvitationStatus.DECLINED, decided_at=NOW)
    async with tx.begin() as t:
        assert await invitations.update(declined, t, expected=first.status)
    # A second writer that read the open invitation loses: the status moved on.
    async with tx.begin() as t:
        assert not await invitations.update(
            replace(first, status=InvitationStatus.ACCEPTED), t, expected=first.status
        )
    assert await invitations.open_for(org.id, "new@example.com") is None
    assert await invitations.get(first.id) == declined
    assert await invitations.list_for_organization(org.id) == [declined]


async def test_audit_and_change_commit_together(database: Database) -> None:
    repo = PostgresOrganizationRepository(database.sessions)
    audit = PostgresAuditLog(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    owner = await add_user(database, "An")
    org = organization()
    actor = Actor(owner, False, {org.id: Role.OWNER})
    async with tx.begin() as t:
        await repo.create(org, owner, t)
        await audit.record(
            new_event(
                actor, AuditAction.ORGANIZATION_CREATED, NOW, organization_id=org.id
            ),
            t,
        )
    with pytest.raises(RuntimeError):
        async with tx.begin() as t:
            await repo.rename(org.id, "Renamed", NOW, t)
            await audit.record(
                new_event(
                    actor, AuditAction.ORGANIZATION_RENAMED, NOW, organization_id=org.id
                ),
                t,
            )
            raise RuntimeError("boom")

    stored = await repo.get(org.id)
    assert stored is not None and stored.name == org.name
    events = await audit.for_organization(org.id, limit=10, cursor=None)
    assert [e.action for e in events] == [AuditAction.ORGANIZATION_CREATED]


async def test_audit_pages_newest_first(database: Database) -> None:
    audit = PostgresAuditLog(database.sessions)
    tx = PostgresTransactionFactory(database.sessions)
    user = await add_user(database, "An")
    actor = Actor(user, False, {})
    for minutes in range(3):
        async with tx.begin() as t:
            await audit.record(
                new_event(
                    actor,
                    AuditAction.USER_ENABLED,
                    NOW + timedelta(minutes=minutes),
                    subject_user_id=user,
                    n=minutes,
                ),
                t,
            )
    first = await audit.for_user(user, limit=2, cursor=None)
    assert [e.details["n"] for e in first] == [2, 1]
    last = first[-1]
    rest = await audit.for_user(user, limit=2, cursor=(last.occurred_at, last.id.hex))
    assert [e.details["n"] for e in rest] == [0]
    assert len(await audit.all(limit=10, cursor=None)) == 3
