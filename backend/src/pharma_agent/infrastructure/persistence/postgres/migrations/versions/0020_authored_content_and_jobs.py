"""Authored documents, glossary entries, colloquial names and ingest jobs.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-11 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "colloquial_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("visual_sign", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "product_names",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "section_keys",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["corpus.collections.id"],
            name=op.f("fk_colloquial_mappings_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_colloquial_mappings")),
        sa.UniqueConstraint(
            "collection_id", "key", name="uq_colloquial_mappings_collection_key"
        ),
        schema="corpus",
    )
    op.create_table(
        "glossary_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column(
            "case_sensitive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "vietnamese_expansions",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "english_expansions",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["corpus.collections.id"],
            name=op.f("fk_glossary_entries_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_glossary_entries")),
        sa.UniqueConstraint(
            "collection_id", "term", name="uq_glossary_entries_collection_term"
        ),
        schema="corpus",
    )
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source_title", sa.Text(), server_default="", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('drug_monograph', 'general_monograph', 'leaflet')",
            name=op.f("ck_source_documents_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["corpus.collections.id"],
            name=op.f("fk_source_documents_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["user.id"],
            name=op.f("fk_source_documents_created_by_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["user.id"],
            name=op.f("fk_source_documents_updated_by_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
        sa.UniqueConstraint(
            "collection_id", "key", name="uq_source_documents_collection_key"
        ),
        schema="corpus",
    )
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("release_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed')",
            name=op.f("ck_ingest_jobs_status"),
        ),
        sa.CheckConstraint(
            "step IN ('bundle', 'chunk', 'embed', 'index', 'publish')",
            name=op.f("ck_ingest_jobs_step"),
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["corpus.collections.id"],
            name=op.f("fk_ingest_jobs_collection_id_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["corpus.releases.id"],
            name=op.f("fk_ingest_jobs_release_id_releases"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["user.id"],
            name=op.f("fk_ingest_jobs_requested_by_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_jobs")),
        schema="corpus",
    )
    op.create_index(
        "ix_ingest_jobs_created",
        "ingest_jobs",
        ["created_at", "id"],
        unique=False,
        schema="corpus",
    )
    op.create_index(
        "uq_ingest_jobs_open",
        "ingest_jobs",
        ["collection_id"],
        unique=True,
        schema="corpus",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ingest_jobs_open",
        table_name="ingest_jobs",
        schema="corpus",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index("ix_ingest_jobs_created", table_name="ingest_jobs", schema="corpus")
    op.drop_table("ingest_jobs", schema="corpus")
    op.drop_table("source_documents", schema="corpus")
    op.drop_table("glossary_entries", schema="corpus")
    op.drop_table("colloquial_mappings", schema="corpus")
