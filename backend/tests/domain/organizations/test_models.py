import uuid
from datetime import UTC, datetime, timedelta

from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.organizations.models import (
    INVITATION_TTL,
    Invitation,
    InvitationStatus,
    generate_invitation_token,
    invitation_token_hash,
    organization_name_problem,
)

NOW = datetime(2026, 10, 11, tzinfo=UTC)


def invitation(status: InvitationStatus, expires_at: datetime | None) -> Invitation:
    return Invitation(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email="an@example.com",
        role=Role.MEMBER,
        invited_by=uuid.uuid4(),
        status=status,
        token_hash="h",
        created_at=NOW,
        expires_at=expires_at,
        decided_by=None,
        decided_at=None,
    )


def test_sent_invitations_expire_after_seven_days() -> None:
    sent = invitation(InvitationStatus.SENT, NOW + INVITATION_TTL)
    just_before = NOW + INVITATION_TTL - timedelta(seconds=1)
    assert sent.effective_status(just_before) is InvitationStatus.SENT
    assert sent.effective_status(NOW + INVITATION_TTL) is InvitationStatus.EXPIRED
    pending = invitation(InvitationStatus.PENDING_APPROVAL, None)
    later = NOW + timedelta(days=30)
    assert pending.effective_status(later) is InvitationStatus.PENDING_APPROVAL


def test_tokens_are_hashed_and_names_are_bounded() -> None:
    token = generate_invitation_token()
    assert len(token) >= 32 and invitation_token_hash(token) != token
    assert invitation_token_hash(token) == invitation_token_hash(token)
    assert organization_name_problem("  ") == "the name is required"
    assert organization_name_problem("x" * 101) == "the name is too long"
    assert organization_name_problem(" Khoa Dược ") is None


def test_superadmin_flag_marks_only_actions_outside_their_memberships() -> None:
    org = uuid.uuid4()
    admin = Actor(uuid.uuid4(), True, {})
    owner_admin = Actor(uuid.uuid4(), True, {org: Role.OWNER})
    outside = new_event(
        admin, AuditAction.ORGANIZATION_RENAMED, NOW, organization_id=org
    )
    inside = new_event(
        owner_admin,
        AuditAction.ORGANIZATION_RENAMED,
        NOW,
        organization_id=org,
        name="X",
    )
    assert outside.actor_was_superadmin and not inside.actor_was_superadmin
    assert (
        inside.details == {"name": "X"} and inside.actor_user_id == owner_admin.user_id
    )
