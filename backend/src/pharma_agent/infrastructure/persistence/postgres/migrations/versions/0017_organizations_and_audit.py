"""Organizations, members, invitations, audit events and quota overrides.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-11 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("text_quota_bytes", sa.BigInteger(), nullable=True))
    op.add_column("user", sa.Column("collection_quota", sa.Integer(), nullable=True))
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("text_quota_bytes", sa.BigInteger(), nullable=True),
        sa.Column("collection_quota", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "organization_members",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'member')",
            name=op.f("ck_organization_members_role"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_organization_members_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "user_id", name=op.f("pk_organization_members")
        ),
    )
    op.create_index(
        "ix_organization_members_user_id", "organization_members", ["user_id"]
    )
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'sent', 'accepted', 'declined',"
            " 'rejected', 'revoked', 'expired')",
            name=op.f("ck_organization_invitations_status"),
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'member')",
            name=op.f("ck_organization_invitations_role"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_invitations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["user.id"],
            name=op.f("fk_organization_invitations_invited_by_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["user.id"],
            name=op.f("fk_organization_invitations_decided_by_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_invitations")),
    )
    op.create_index(
        "uq_organization_invitations_open",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_approval', 'sent')"),
    )
    op.create_index(
        "ix_organization_invitations_token_hash",
        "organization_invitations",
        ["token_hash"],
        unique=True,
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_was_superadmin", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("subject_user_id", sa.Uuid(), nullable=True),
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user.id"],
            name=op.f("fk_audit_events_actor_user_id_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_organization_occurred",
        "audit_events",
        ["organization_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_audit_events_subject_occurred",
        "audit_events",
        ["subject_user_id", "occurred_at", "id"],
    )
    op.create_index("ix_audit_events_occurred", "audit_events", ["occurred_at", "id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("organization_invitations")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_column("user", "collection_quota")
    op.drop_column("user", "text_quota_bytes")
