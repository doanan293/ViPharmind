import uuid
from datetime import datetime
from typing import Protocol

from pharma_agent.domain.access.models import Role
from pharma_agent.domain.organizations.models import (
    Invitation,
    InvitationStatus,
    Membership,
    MemberView,
    Organization,
)
from pharma_agent.domain.shared.errors import DomainError
from pharma_agent.domain.shared.transaction import Transaction


class InvitationConflict(DomainError):
    """The organization already has an open invitation for this email."""

    code = "INVITATION_CONFLICT"


class MembershipLookup(Protocol):
    """The part of OrganizationRepository the account page needs."""

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]: ...


class OrganizationRepository(Protocol):
    async def get(self, organization_id: uuid.UUID) -> Organization | None: ...

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]: ...

    async def list_all(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[Organization]:
        """Newest first, keyset on (created_at, id)."""
        ...

    async def member_count(self, organization_id: uuid.UUID) -> int: ...

    async def create(
        self, organization: Organization, owner_id: uuid.UUID, tx: Transaction
    ) -> None:
        """Insert the organization with `owner_id` as its first owner."""
        ...

    async def rename(
        self, organization_id: uuid.UUID, name: str, now: datetime, tx: Transaction
    ) -> None: ...

    async def set_quotas(
        self,
        organization_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
        now: datetime,
        tx: Transaction,
    ) -> None: ...

    async def delete(self, organization_id: uuid.UUID, tx: Transaction) -> None: ...

    async def members(self, organization_id: uuid.UUID) -> list[MemberView]: ...

    async def memberships_of(self, user_id: uuid.UUID) -> dict[uuid.UUID, Role]: ...

    async def owner_count(self, organization_id: uuid.UUID) -> int: ...

    async def add_member(self, membership: Membership, tx: Transaction) -> None: ...

    async def set_role(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        tx: Transaction,
    ) -> None: ...

    async def remove_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, tx: Transaction
    ) -> bool: ...


class InvitationRepository(Protocol):
    async def get(self, invitation_id: uuid.UUID) -> Invitation | None: ...

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None: ...

    async def list_for_organization(
        self, organization_id: uuid.UUID
    ) -> list[Invitation]:
        """Newest first."""
        ...

    async def open_for(
        self, organization_id: uuid.UUID, email: str
    ) -> Invitation | None: ...

    async def create(self, invitation: Invitation, tx: Transaction) -> None:
        """Raises InvitationConflict when an open invitation exists for the email."""
        ...

    async def update(
        self, invitation: Invitation, tx: Transaction, *, expected: InvitationStatus
    ) -> bool:
        """Write status, token hash, deadline and decision fields if the stored status is
        still `expected`; False when another request changed it first."""
        ...
