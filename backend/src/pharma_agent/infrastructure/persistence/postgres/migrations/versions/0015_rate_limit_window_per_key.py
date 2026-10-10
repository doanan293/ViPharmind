"""Rate-limit windows open at a key's first action: one bucket row per key.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-10 20:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Buckets live an hour at most; dropping them only resets the current limits.
    op.execute("DELETE FROM rate_limit_buckets")
    op.drop_constraint("pk_rate_limit_buckets", "rate_limit_buckets", type_="primary")
    op.create_primary_key("pk_rate_limit_buckets", "rate_limit_buckets", ["key"])


def downgrade() -> None:
    op.drop_constraint("pk_rate_limit_buckets", "rate_limit_buckets", type_="primary")
    op.create_primary_key(
        "pk_rate_limit_buckets", "rate_limit_buckets", ["key", "window_start"]
    )
