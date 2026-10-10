"""Organizations, memberships and invitations (spec §4.1-§4.3)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from pharma_agent.domain.access.models import Role

INVITATION_TTL = timedelta(days=7)
NAME_MAX_LENGTH = 100


class InvitationStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


OPEN_STATUSES = frozenset({InvitationStatus.PENDING_APPROVAL, InvitationStatus.SENT})


@dataclass(frozen=True)
class Organization:
    id: uuid.UUID
    name: str
    text_quota_bytes: int | None
    collection_quota: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Membership:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    joined_at: datetime


@dataclass(frozen=True)
class MemberView:
    user_id: uuid.UUID
    display_name: str
    email: str | None
    role: Role
    joined_at: datetime


@dataclass(frozen=True)
class Invitation:
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: Role
    invited_by: uuid.UUID | None
    status: InvitationStatus
    token_hash: str
    created_at: datetime
    expires_at: datetime | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None

    def effective_status(self, now: datetime) -> InvitationStatus:
        """A sent invitation past its deadline reads as expired before cleanup marks it."""
        if (
            self.status is InvitationStatus.SENT
            and self.expires_at is not None
            and now >= self.expires_at
        ):
            return InvitationStatus.EXPIRED
        return self.status


def generate_invitation_token() -> str:
    return secrets.token_urlsafe(32)


def invitation_token_hash(token: str) -> str:
    """Only the hash is stored, so a database leak does not hand out working links."""
    return hashlib.sha256(token.encode()).hexdigest()


def organization_name_problem(name: str) -> str | None:
    stripped = name.strip()
    if not stripped:
        return "the name is required"
    if len(stripped) > NAME_MAX_LENGTH:
        return "the name is too long"
    return None
