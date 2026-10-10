"""Drop corpus data nothing reads: the glossary and colloquial tables and unread columns.

Enrichment results live on each chunk version (term_annotations, colloquial), and citations
and hydration read only keys, titles and headings. The dropped values stay in the knowledge
bundle. Downgrade restores the schema. Existing rows get placeholder values in the restored
NOT NULL columns, which the earlier service version only ever wrote.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "corpus"


def upgrade() -> None:
    op.drop_table("colloquial_mappings", schema=SCHEMA)
    op.drop_table("glossary_entries", schema=SCHEMA)
    for column in ("blocks", "start_page", "end_page", "char_count"):
        op.drop_column("section_revisions", column, schema=SCHEMA)
    for column in ("context_path", "ordinal", "retrieval_mode"):
        op.drop_column("sections", column, schema=SCHEMA)
    for column in ("kind", "source_url", "attributes"):
        op.drop_column("documents", column, schema=SCHEMA)


def _add_required(table: str, column: sa.Column, placeholder: str) -> None:
    column.server_default = sa.DefaultClause(sa.text(placeholder))
    op.add_column(table, column, schema=SCHEMA)
    op.alter_column(table, column.name, server_default=None, schema=SCHEMA)


def downgrade() -> None:
    _add_required(
        "documents", sa.Column("kind", sa.String(length=32), nullable=False), "''"
    )
    op.add_column(
        "documents", sa.Column("source_url", sa.Text(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "documents",
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "sections",
        sa.Column(
            "context_path",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    _add_required("sections", sa.Column("ordinal", sa.Integer(), nullable=False), "0")
    _add_required(
        "sections",
        sa.Column("retrieval_mode", sa.String(length=16), nullable=False),
        "''",
    )
    _add_required(
        "section_revisions",
        sa.Column("blocks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        "'[]'::jsonb",
    )
    op.add_column(
        "section_revisions",
        sa.Column("start_page", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "section_revisions",
        sa.Column("end_page", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    _add_required(
        "section_revisions", sa.Column("char_count", sa.Integer(), nullable=False), "0"
    )
    op.create_table(
        "glossary_entries",
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["corpus.releases.id"],
            name=op.f("fk_glossary_entries_release_id_releases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("release_id", "term", name=op.f("pk_glossary_entries")),
        schema=SCHEMA,
    )
    op.create_table(
        "colloquial_mappings",
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["corpus.releases.id"],
            name=op.f("fk_colloquial_mappings_release_id_releases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "release_id", "position", name=op.f("pk_colloquial_mappings")
        ),
        schema=SCHEMA,
    )
