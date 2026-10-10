"""OrganizationRepository over `organizations` and `organization_members`."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Row,
    Uuid,
    delete,
    func,
    insert,
    literal,
    select,
    tuple_,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.access.models import Role
from pharma_agent.domain.organizations.models import (
    Membership,
    MemberView,
    Organization,
)
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.tables import (
    OrganizationMemberTable,
    OrganizationTable,
    UserTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_org = OrganizationTable.__table__.c
_member = OrganizationMemberTable.__table__.c
_user = UserTable.__table__.c


def _organization(
    row: Row[tuple[OrganizationTable]] | OrganizationTable,
) -> Organization:
    record = row if isinstance(row, OrganizationTable) else row[0]
    return Organization(
        id=record.id,
        name=record.name,
        text_quota_bytes=record.text_quota_bytes,
        collection_quota=record.collection_quota,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class PostgresOrganizationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        async with self._sessions() as session:
            row = await session.get(OrganizationTable, organization_id)
        return None if row is None else _organization(row)

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]:
        query = (
            select(OrganizationTable, _member.role)
            .join(
                OrganizationMemberTable,
                _member.organization_id == _org.id,
            )
            .where(_member.user_id == user_id)
            .order_by(_org.name, _org.id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return [(_organization(org), Role(role)) for org, role in rows]

    async def list_all(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[Organization]:
        query = select(OrganizationTable).order_by(
            _org.created_at.desc(), _org.id.desc()
        )
        if cursor is not None:
            at, key = cursor
            query = query.where(
                tuple_(_org.created_at, _org.id)
                < tuple_(
                    literal(at, DateTime(timezone=True)),
                    literal(uuid.UUID(hex=key), Uuid()),
                )
            )
        async with self._sessions() as session:
            rows = (await session.scalars(query.limit(limit))).all()
        return [_organization(row) for row in rows]

    async def member_count(self, organization_id: uuid.UUID) -> int:
        query = select(func.count()).where(_member.organization_id == organization_id)
        async with self._sessions() as session:
            return (await session.execute(query)).scalar_one()

    async def create(
        self, organization: Organization, owner_id: uuid.UUID, tx: Transaction
    ) -> None:
        session = session_of(tx)
        await session.execute(
            insert(OrganizationTable).values(
                id=organization.id,
                name=organization.name,
                text_quota_bytes=organization.text_quota_bytes,
                collection_quota=organization.collection_quota,
                created_at=organization.created_at,
                updated_at=organization.updated_at,
            )
        )
        await session.execute(
            insert(OrganizationMemberTable).values(
                organization_id=organization.id,
                user_id=owner_id,
                role=Role.OWNER.value,
                joined_at=organization.created_at,
            )
        )

    async def rename(
        self, organization_id: uuid.UUID, name: str, now: datetime, tx: Transaction
    ) -> None:
        await session_of(tx).execute(
            update(OrganizationTable)
            .where(_org.id == organization_id)
            .values(name=name, updated_at=now)
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
        await session_of(tx).execute(
            update(OrganizationTable)
            .where(_org.id == organization_id)
            .values(
                text_quota_bytes=text_quota_bytes,
                collection_quota=collection_quota,
                updated_at=now,
            )
        )

    async def delete(self, organization_id: uuid.UUID, tx: Transaction) -> None:
        await session_of(tx).execute(
            delete(OrganizationTable).where(_org.id == organization_id)
        )

    async def members(self, organization_id: uuid.UUID) -> list[MemberView]:
        query = (
            select(
                _member.user_id,
                _user.display_name,
                _user.email,
                _member.role,
                _member.joined_at,
            )
            .join(UserTable, _user.id == _member.user_id)
            .where(_member.organization_id == organization_id)
            .order_by(_member.joined_at, _member.user_id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return [
            MemberView(
                user_id=user_id,
                display_name=display_name,
                email=email or None,
                role=Role(role),
                joined_at=joined_at,
            )
            for user_id, display_name, email, role, joined_at in rows
        ]

    async def memberships_of(self, user_id: uuid.UUID) -> dict[uuid.UUID, Role]:
        query = select(_member.organization_id, _member.role).where(
            _member.user_id == user_id
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).all()
        return {organization_id: Role(role) for organization_id, role in rows}

    async def owner_count(self, organization_id: uuid.UUID) -> int:
        query = select(func.count()).where(
            _member.organization_id == organization_id,
            _member.role == Role.OWNER.value,
        )
        async with self._sessions() as session:
            return (await session.execute(query)).scalar_one()

    async def add_member(self, membership: Membership, tx: Transaction) -> None:
        await session_of(tx).execute(
            insert(OrganizationMemberTable).values(
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                role=membership.role.value,
                joined_at=membership.joined_at,
            )
        )

    async def set_role(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        tx: Transaction,
    ) -> None:
        await session_of(tx).execute(
            update(OrganizationMemberTable)
            .where(
                _member.organization_id == organization_id,
                _member.user_id == user_id,
            )
            .values(role=role.value)
        )

    async def remove_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, tx: Transaction
    ) -> bool:
        result = await session_of(tx).execute(
            delete(OrganizationMemberTable)
            .where(
                _member.organization_id == organization_id,
                _member.user_id == user_id,
            )
            .returning(_member.user_id)
        )
        return result.first() is not None
