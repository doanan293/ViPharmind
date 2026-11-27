"""Who is acting: the user, their superadmin flag, and their role in each organization."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """A member's role in an organization; ROLE_RANK orders member < editor < owner."""

    OWNER = "owner"
    EDITOR = "editor"
    MEMBER = "member"


ROLE_RANK: dict[Role, int] = {Role.MEMBER: 0, Role.EDITOR: 1, Role.OWNER: 2}


@dataclass(frozen=True)
class Actor:
    """The acting user, whether they are superadmin, and their role per organization."""

    user_id: uuid.UUID
    is_superadmin: bool
    memberships: Mapping[uuid.UUID, Role]

    def role_in(self, organization_id: uuid.UUID) -> Role | None:
        """The actor's role in the organization, or None when not a member."""
        return self.memberships.get(organization_id)
