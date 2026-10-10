"""Emails are unique ignoring case, matching how every lookup compares them.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_user_email_lower", "user", [sa.text("lower(email)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_user_email_lower", table_name="user")
