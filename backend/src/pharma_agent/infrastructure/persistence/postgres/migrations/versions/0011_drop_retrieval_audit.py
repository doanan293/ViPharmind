"""Drop the write-only chat data: retrieval_runs, retrieval_hits and messages.phases.

Nothing read them back. Retrieval analysis runs in pharma-lab and Langfuse, and the history
API never returned the phases. Downgrade restores the empty tables and column.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("retrieval_hits")
    op.drop_index("ix_retrieval_runs_message", table_name="retrieval_runs")
    op.drop_table("retrieval_runs")
    op.drop_column("messages", "phases")


def downgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "phases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column(
            "retriever_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "release_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_retrieval_runs_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_retrieval_runs_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_runs")),
    )
    op.create_index(
        "ix_retrieval_runs_message", "retrieval_runs", ["message_id"], unique=False
    )
    op.create_table(
        "retrieval_hits",
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("fusion_score", sa.Float(), nullable=False),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("hydrate_strategy", sa.String(length=32), nullable=False),
        sa.Column(
            "cited", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("snippet", sa.Text(), server_default="", nullable=False),
        sa.Column("chunk_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_key", sa.Text(), nullable=False),
        sa.Column("table_key", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            name=op.f("fk_retrieval_hits_retrieval_run_id_retrieval_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "retrieval_run_id", "rank", name=op.f("pk_retrieval_hits")
        ),
    )
