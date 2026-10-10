"""Corpus cleanup: vectors live only in Qdrant, embedding text is derived, drop leftovers.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-11 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORPUS_TABLES = (
    "chunk_versions",
    "section_revisions",
    "release_chunks",
    "sections",
    "documents",
)


def upgrade() -> None:
    op.drop_table("embedding_cache", schema="corpus")
    op.drop_column("chunk_versions", "embedding_text", schema="corpus")
    # Left over from migrations removed in commit ab5d822; never part of the models.
    op.execute("DROP TABLE IF EXISTS public.skills")
    # VACUUM cannot run inside a transaction; Alembic opens one per migration.
    with op.get_context().autocommit_block():
        for table in CORPUS_TABLES:
            op.execute(f"VACUUM FULL corpus.{table}")


def downgrade() -> None:
    op.add_column(
        "chunk_versions",
        sa.Column("embedding_text", sa.Text(), nullable=False, server_default=""),
        schema="corpus",
    )
    op.alter_column(
        "chunk_versions", "embedding_text", server_default=None, schema="corpus"
    )
    op.create_table(
        "embedding_cache",
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("embedding_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "model", "embedding_text_sha256", name=op.f("pk_embedding_cache")
        ),
        schema="corpus",
    )
