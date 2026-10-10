"""Who is acting: the user, their superadmin flag, and their role in each organization."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    MEMBER = "member"


ROLE_RANK: dict[Role, int] = {Role.MEMBER: 0, Role.EDITOR: 1, Role.OWNER: 2}


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    is_superadmin: bool
    memberships: Mapping[uuid.UUID, Role]

    def role_in(self, organization_id: uuid.UUID) -> Role | None:
        return self.memberships.get(organization_id)
