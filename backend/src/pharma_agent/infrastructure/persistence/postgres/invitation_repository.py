"""InvitationRepository over `organization_invitations`."""

import uuid

from sqlalchemy import ColumnElement, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.access.models import Role
from pharma_agent.domain.organizations.models import (
    OPEN_STATUSES,
    Invitation,
    InvitationStatus,
)
from pharma_agent.domain.organizations.ports import InvitationConflict
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.tables import (
    OrganizationInvitationTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_inv = OrganizationInvitationTable.__table__.c
_OPEN = [status.value for status in OPEN_STATUSES]


def _invitation(row: OrganizationInvitationTable) -> Invitation:
    return Invitation(
        id=row.id,
        organization_id=row.organization_id,
        email=row.email,
        role=Role(row.role),
        invited_by=row.invited_by,
        status=InvitationStatus(row.status),
        token_hash=row.token_hash,
        created_at=row.created_at,
        expires_at=row.expires_at,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
    )


class PostgresInvitationRepository:
    """InvitationRepository over `organization_invitations`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Read through sessions from `sessions`; writes use the caller's transaction."""
        self._sessions = sessions

    async def _one(self, *conditions: ColumnElement[bool]) -> Invitation | None:
        query = select(OrganizationInvitationTable).where(*conditions)
        async with self._sessions() as session:
            row = (await session.scalars(query)).first()
        return None if row is None else _invitation(row)

    async def get(self, invitation_id: uuid.UUID) -> Invitation | None:
        """The invitation, or None if there is no such id."""
        return await self._one(_inv.id == invitation_id)

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        """The invitation whose token hashes to `token_hash`, if any."""
        return await self._one(_inv.token_hash == token_hash)

    async def list_for_organization(
        self, organization_id: uuid.UUID
    ) -> list[Invitation]:
        """The organization's invitations, newest first."""
        query = (
            select(OrganizationInvitationTable)
            .where(_inv.organization_id == organization_id)
            .order_by(_inv.created_at.desc(), _inv.id.desc())
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [_invitation(row) for row in rows]

    async def open_for(
        self, organization_id: uuid.UUID, email: str
    ) -> Invitation | None:
        """The organization's pending or sent invitation for `email`, if any."""
        return await self._one(
            _inv.organization_id == organization_id,
            _inv.email == email,
            _inv.status.in_(_OPEN),
        )

    async def create(self, invitation: Invitation, tx: Transaction) -> None:
        """Insert the invitation inside `tx`.

        Raises:
            InvitationConflict: An open invitation exists for the email. A savepoint keeps `tx`
                usable.
        """
        session = session_of(tx)
        try:
            # A savepoint keeps the caller's transaction usable after the conflict.
            async with session.begin_nested():
                await session.execute(
                    insert(OrganizationInvitationTable).values(
                        id=invitation.id,
                        organization_id=invitation.organization_id,
                        email=invitation.email,
                        role=invitation.role.value,
                        invited_by=invitation.invited_by,
                        status=invitation.status.value,
                        token_hash=invitation.token_hash,
                        created_at=invitation.created_at,
                        expires_at=invitation.expires_at,
                        decided_by=invitation.decided_by,
                        decided_at=invitation.decided_at,
                    )
                )
        except IntegrityError as exc:
            raise InvitationConflict(
                f"an invitation for {invitation.email} is already open"
            ) from exc

    async def update(
        self, invitation: Invitation, tx: Transaction, *, expected: InvitationStatus
    ) -> bool:
        """Write the mutable fields if the stored status is still `expected`.

        Returns:
            False when another request changed the status first.
        """
        result = await session_of(tx).execute(
            update(OrganizationInvitationTable)
            .where(_inv.id == invitation.id, _inv.status == expected.value)
            .values(
                role=invitation.role.value,
                status=invitation.status.value,
                token_hash=invitation.token_hash,
                expires_at=invitation.expires_at,
                decided_by=invitation.decided_by,
                decided_at=invitation.decided_at,
            )
            .returning(_inv.id)
        )
        return result.scalar_one_or_none() is not None
