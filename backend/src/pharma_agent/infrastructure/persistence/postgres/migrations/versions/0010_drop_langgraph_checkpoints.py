"""Drop the LangGraph checkpoint tables: chat turns no longer run with a checkpointer.

The tables were created by langgraph-checkpoint-postgres (AsyncPostgresSaver.setup), not by
Alembic, so a database that never ran a chat turn may not have them. Downgrade does not
recreate them, because the earlier service version creates them itself on start.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKPOINT_TABLES = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
    "checkpoint_migrations",
)


def upgrade() -> None:
    for table in CHECKPOINT_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    pass
