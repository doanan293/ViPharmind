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
    ) -> list[tuple[Organization, Role]]:
        """The user's organizations with the user's role in each, ordered by name."""
        ...


class OrganizationRepository(Protocol):
    """Storage of organizations and their memberships."""

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        """The organization, or None if there is no such id."""
        ...

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]:
        """The user's organizations with the user's role in each, ordered by name."""
        ...

    async def list_all(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[Organization]:
        """Newest first, keyset on (created_at, id)."""
        ...

    async def member_count(self, organization_id: uuid.UUID) -> int:
        """Number of members of the organization."""
        ...

    async def create(
        self, organization: Organization, owner_id: uuid.UUID, tx: Transaction
    ) -> None:
        """Insert the organization with `owner_id` as its first owner."""
        ...

    async def rename(
        self, organization_id: uuid.UUID, name: str, now: datetime, tx: Transaction
    ) -> None:
        """Change the organization's name inside `tx`."""
        ...

    async def set_quotas(
        self,
        organization_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
        now: datetime,
        tx: Transaction,
    ) -> None:
        """Overwrite both quota overrides inside `tx`; None uses the default."""
        ...

    async def delete(self, organization_id: uuid.UUID, tx: Transaction) -> None:
        """Delete the organization inside `tx`, with its members and invitations.

        Its collections are only marked deleted, so cited chunks survive.
        """
        ...

    async def members(self, organization_id: uuid.UUID) -> list[MemberView]:
        """The organization's members with names and roles, longest-standing first."""
        ...

    async def memberships_of(self, user_id: uuid.UUID) -> dict[uuid.UUID, Role]:
        """The user's role per organization id, for every organization they are in."""
        ...

    async def owner_count(self, organization_id: uuid.UUID) -> int:
        """Number of owners of the organization."""
        ...

    async def add_member(self, membership: Membership, tx: Transaction) -> None:
        """Insert the membership inside `tx`."""
        ...

    async def set_role(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        tx: Transaction,
    ) -> None:
        """Change a member's role inside `tx`; does nothing for a non-member."""
        ...

    async def remove_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, tx: Transaction
    ) -> bool:
        """Delete the membership inside `tx`; False if the user was not a member."""
        ...


class InvitationRepository(Protocol):
    """Storage of organization invitations."""

    async def get(self, invitation_id: uuid.UUID) -> Invitation | None:
        """The invitation, or None if there is no such id."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        """The invitation whose token hashes to `token_hash`, if any."""
        ...

    async def list_for_organization(
        self, organization_id: uuid.UUID
    ) -> list[Invitation]:
        """Newest first."""
        ...

    async def open_for(
        self, organization_id: uuid.UUID, email: str
    ) -> Invitation | None:
        """The organization's pending or sent invitation for `email`, if any."""
        ...

    async def create(self, invitation: Invitation, tx: Transaction) -> None:
        """Raises InvitationConflict when an open invitation exists for the email."""
        ...

    async def update(
        self, invitation: Invitation, tx: Transaction, *, expected: InvitationStatus
    ) -> bool:
        """Write status, token hash, deadline and decision fields.

        Only when the stored status is still `expected`; False when another request
        changed it first.
        """
        ...
