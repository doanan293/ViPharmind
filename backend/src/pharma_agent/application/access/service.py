"""Resolve who is acting for each request."""

import uuid

from pharma_agent.application.errors import AccountNotFound
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.account.ports import AccountRepository
from pharma_agent.domain.organizations.ports import OrganizationRepository

__all__ = ["Actor", "ActorResolver", "Role"]


class ActorResolver:
    """Reads the user's superadmin flag and memberships fresh on every call, so a role
    change or a removal applies to the very next request."""

    def __init__(
        self, accounts: AccountRepository, organizations: OrganizationRepository
    ) -> None:
        self._accounts = accounts
        self._organizations = organizations

    async def resolve(self, user_id: uuid.UUID) -> Actor:
        user = await self._accounts.get(user_id)
        if user is None:
            raise AccountNotFound(str(user_id))
        memberships = await self._organizations.memberships_of(user_id)
        return Actor(user_id, user.is_superuser, memberships)
