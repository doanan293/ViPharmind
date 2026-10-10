"""Audit events: who did what to which organization, user or collection."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pharma_agent.domain.access.models import Actor


class AuditAction(StrEnum):
    ORGANIZATION_CREATED = "organization.created"
    ORGANIZATION_RENAMED = "organization.renamed"
    ORGANIZATION_DELETED = "organization.deleted"
    MEMBER_JOINED = "member.joined"
    MEMBER_LEFT = "member.left"
    MEMBER_REMOVED = "member.removed"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    INVITATION_CREATED = "invitation.created"
    INVITATION_APPROVED = "invitation.approved"
    INVITATION_REJECTED = "invitation.rejected"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_DECLINED = "invitation.declined"
    INVITATION_RESENT = "invitation.resent"
    COLLECTION_CREATED = "collection.created"
    COLLECTION_RENAMED = "collection.renamed"
    COLLECTION_DELETED = "collection.deleted"
    COLLECTION_VISIBILITY_CHANGED = "collection.visibility_changed"
    COLLECTION_PUBLISHED = "collection.published"
    COLLECTION_ROLLED_BACK = "collection.rolled_back"
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    GLOSSARY_UPDATED = "glossary.updated"
    COLLOQUIAL_UPDATED = "colloquial.updated"
    USER_DISABLED = "user.disabled"
    USER_ENABLED = "user.enabled"
    QUOTA_CHANGED = "quota.changed"


@dataclass(frozen=True)
class AuditEvent:
    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_was_superadmin: bool
    action: AuditAction
    organization_id: uuid.UUID | None
    subject_user_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    details: Mapping[str, object] = field(default_factory=dict)


def new_event(
    actor: Actor,
    action: AuditAction,
    now: datetime,
    *,
    organization_id: uuid.UUID | None = None,
    subject_user_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    **details: object,
) -> AuditEvent:
    """`subject_user_id` is the user the event is about; for a personal collection it is
    the collection's owner, so the owner's activity page lists it.

    The superadmin flag is set only when the action needed superadmin rights: outside the
    actor's own organizations and not about the actor's own account.
    """
    acting_on_own = (
        organization_id is not None and actor.role_in(organization_id) is not None
    ) or (organization_id is None and subject_user_id == actor.user_id)
    return AuditEvent(
        id=uuid.uuid4(),
        occurred_at=now,
        actor_user_id=actor.user_id,
        actor_was_superadmin=actor.is_superadmin and not acting_on_own,
        action=action,
        organization_id=organization_id,
        subject_user_id=subject_user_id,
        collection_id=collection_id,
        details=dict(details),
    )
