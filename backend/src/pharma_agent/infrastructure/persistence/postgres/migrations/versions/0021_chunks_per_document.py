"""Chunks belong to documents: no section revisions, no hydrate columns.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-15 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Chunks are re-cut per document; every published release and its citations are
    # rebuilt from the bundle, so the old rows go (production starts from an empty
    # database).
    op.execute("DELETE FROM message_citations")
    op.execute("UPDATE corpus.collections SET current_release_id = NULL")
    op.execute("DELETE FROM corpus.release_chunks")
    op.execute("DELETE FROM corpus.chunk_versions")
    op.execute("DELETE FROM corpus.releases")
    op.drop_constraint(
        op.f("ck_message_citations_strategy"), "message_citations", type_="check"
    )
    op.drop_column("message_citations", "strategy")
    op.drop_column("message_citations", "block_chunk_version_ids")
    op.drop_index(
        "ix_release_chunks_release_revision_ordinal",
        table_name="release_chunks",
        schema="corpus",
    )
    op.drop_column("release_chunks", "hydrate_strategy", schema="corpus")
    op.drop_column("release_chunks", "section_revision_id", schema="corpus")
    op.drop_column("release_chunks", "section_id", schema="corpus")
    op.add_column(
        "release_chunks",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "corpus.documents.id",
                name=op.f("fk_release_chunks_document_id_documents"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        schema="corpus",
    )
    op.create_index(
        "ix_release_chunks_release_document_ordinal",
        "release_chunks",
        ["release_id", "document_id", "ordinal"],
        schema="corpus",
    )
    op.drop_column("chunk_versions", "section_revision_id", schema="corpus")
    op.drop_column("chunk_versions", "kind", schema="corpus")
    op.drop_column("chunk_versions", "table_key", schema="corpus")
    op.add_column(
        "chunk_versions",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "corpus.documents.id",
                name=op.f("fk_chunk_versions_document_id_documents"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column("section_keys", postgresql.ARRAY(sa.Text()), nullable=False),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column("headings", postgresql.ARRAY(sa.Text()), nullable=False),
        schema="corpus",
    )
    op.create_index(
        "ix_chunk_versions_document_ordinal",
        "chunk_versions",
        ["document_id", "ordinal"],
        schema="corpus",
    )
    op.drop_table("section_revisions", schema="corpus")


def downgrade() -> None:
    # The old layout cannot be rebuilt from document chunks: rows go, the schema returns.
    op.execute("DELETE FROM message_citations")
    op.execute("UPDATE corpus.collections SET current_release_id = NULL")
    op.execute("DELETE FROM corpus.release_chunks")
    op.execute("DELETE FROM corpus.chunk_versions")
    op.execute("DELETE FROM corpus.releases")
    op.create_table(
        "section_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["corpus.sections.id"],
            name=op.f("fk_section_revisions_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section_revisions")),
        schema="corpus",
    )
    op.drop_index(
        "ix_chunk_versions_document_ordinal",
        table_name="chunk_versions",
        schema="corpus",
    )
    op.drop_column("chunk_versions", "headings", schema="corpus")
    op.drop_column("chunk_versions", "section_keys", schema="corpus")
    op.drop_column("chunk_versions", "document_id", schema="corpus")
    op.add_column(
        "chunk_versions",
        sa.Column("table_key", sa.String(length=200), nullable=True),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column("kind", sa.String(length=32), nullable=False),
        schema="corpus",
    )
    op.add_column(
        "chunk_versions",
        sa.Column(
            "section_revision_id",
            sa.Uuid(),
            sa.ForeignKey(
                "corpus.section_revisions.id",
                name=op.f("fk_chunk_versions_section_revision_id_section_revisions"),
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        schema="corpus",
    )
    op.drop_index(
        "ix_release_chunks_release_document_ordinal",
        table_name="release_chunks",
        schema="corpus",
    )
    op.drop_column("release_chunks", "document_id", schema="corpus")
    op.add_column(
        "release_chunks",
        sa.Column(
            "section_id",
            sa.Uuid(),
            sa.ForeignKey(
                "corpus.sections.id",
                name=op.f("fk_release_chunks_section_id_sections"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        schema="corpus",
    )
    op.add_column(
        "release_chunks",
        sa.Column(
            "section_revision_id",
            sa.Uuid(),
            sa.ForeignKey(
                "corpus.section_revisions.id",
                name=op.f("fk_release_chunks_section_revision_id_section_revisions"),
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        schema="corpus",
    )
    op.add_column(
        "release_chunks",
        sa.Column("hydrate_strategy", sa.String(length=32), nullable=False),
        schema="corpus",
    )
    op.create_index(
        "ix_release_chunks_release_revision_ordinal",
        "release_chunks",
        ["release_id", "section_revision_id", "ordinal"],
        schema="corpus",
    )
    op.add_column(
        "message_citations",
        sa.Column(
            "block_chunk_version_ids", postgresql.ARRAY(sa.Uuid()), nullable=False
        ),
    )
    op.add_column(
        "message_citations",
        sa.Column("strategy", sa.String(length=16), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_message_citations_strategy"),
        "message_citations",
        "strategy IN ('search_only', 'chunk_window', 'full_section')",
    )
