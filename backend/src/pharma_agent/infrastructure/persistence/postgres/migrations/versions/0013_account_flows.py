"""Account flows: nullable email, phone sign-in, one-time codes, rate limits, session details.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("user", "email", existing_type=sa.String(length=320), nullable=True)
    op.add_column(
        "user", sa.Column("phone_number", sa.String(length=16), nullable=True)
    )
    op.create_index(op.f("ix_user_phone_number"), "user", ["phone_number"], unique=True)
    op.add_column(
        "user",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column(
            "password_set", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_user_email_or_phone"),
        "user",
        "email IS NOT NULL OR phone_number IS NOT NULL",
    )
    # Accounts fastapi-users already marked verified keep working without a new code.
    op.execute('UPDATE "user" SET email_verified_at = now() WHERE is_verified')

    op.add_column(
        "access_tokens",
        sa.Column(
            "user_agent", sa.String(length=255), server_default="", nullable=False
        ),
    )
    op.add_column(
        "access_tokens",
        sa.Column(
            "ip_address", sa.String(length=45), server_default="", nullable=False
        ),
    )
    op.add_column(
        "access_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "one_time_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_one_time_codes_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_codes")),
    )
    op.create_index(
        "ix_one_time_codes_lookup",
        "one_time_codes",
        ["purpose", "destination", "created_at"],
        unique=False,
    )
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "key", "window_start", name=op.f("pk_rate_limit_buckets")
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_one_time_codes_lookup", table_name="one_time_codes")
    op.drop_table("one_time_codes")
    op.drop_column("access_tokens", "last_used_at")
    op.drop_column("access_tokens", "ip_address")
    op.drop_column("access_tokens", "user_agent")
    op.drop_constraint(op.f("ck_user_email_or_phone"), "user", type_="check")
    op.drop_column("user", "password_set")
    op.drop_column("user", "phone_verified_at")
    op.drop_column("user", "email_verified_at")
    op.drop_index(op.f("ix_user_phone_number"), table_name="user")
    op.drop_column("user", "phone_number")
    # Phone-only accounts cannot exist once email is required again.
    op.execute('DELETE FROM "user" WHERE email IS NULL')
    op.alter_column(
        "user", "email", existing_type=sa.String(length=320), nullable=False
    )
