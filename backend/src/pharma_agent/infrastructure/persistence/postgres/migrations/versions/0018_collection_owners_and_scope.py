"""Collections belong to a user, an organization or the system; conversations keep a scope.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-11 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("owner_organization_id", sa.Uuid(), nullable=True),
        schema="corpus",
    )
    op.create_foreign_key(
        op.f("fk_collections_owner_organization_id_organizations"),
        "collections",
        "organizations",
        ["owner_organization_id"],
        ["id"],
        source_schema="corpus",
        ondelete="CASCADE",
    )
    # Collections without an owner become the public system corpus (spec §4.10).
    op.execute(
        "UPDATE corpus.collections SET visibility = 'public'"
        " WHERE owner_user_id IS NULL"
    )
    op.drop_constraint(
        op.f("ck_collections_visibility"), "collections", schema="corpus", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_collections_visibility"),
        "collections",
        "visibility IN ('private', 'organization', 'public')",
        schema="corpus",
    )
    op.create_check_constraint(
        op.f("ck_collections_one_owner"),
        "collections",
        "owner_user_id IS NULL OR owner_organization_id IS NULL",
        schema="corpus",
    )
    op.create_check_constraint(
        op.f("ck_collections_system_is_public"),
        "collections",
        "owner_user_id IS NOT NULL OR owner_organization_id IS NOT NULL"
        " OR visibility = 'public'",
        schema="corpus",
    )
    op.create_check_constraint(
        op.f("ck_collections_organization_needs_owner"),
        "collections",
        "visibility <> 'organization' OR owner_organization_id IS NOT NULL",
        schema="corpus",
    )
    op.create_index(
        "ix_collections_owner_user_id",
        "collections",
        ["owner_user_id"],
        schema="corpus",
    )
    op.create_index(
        "ix_collections_owner_organization_id",
        "collections",
        ["owner_organization_id"],
        schema="corpus",
    )
    op.add_column(
        "conversations",
        sa.Column("collection_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "collection_ids")
    op.drop_index(
        "ix_collections_owner_organization_id",
        table_name="collections",
        schema="corpus",
    )
    op.drop_index(
        "ix_collections_owner_user_id", table_name="collections", schema="corpus"
    )
    for name in (
        "ck_collections_organization_needs_owner",
        "ck_collections_system_is_public",
        "ck_collections_one_owner",
        "ck_collections_visibility",
    ):
        op.drop_constraint(op.f(name), "collections", schema="corpus", type_="check")
    op.execute(
        "UPDATE corpus.collections SET visibility = 'private'"
        " WHERE visibility = 'organization'"
    )
    op.create_check_constraint(
        op.f("ck_collections_visibility"),
        "collections",
        "visibility IN ('private', 'public')",
        schema="corpus",
    )
    op.drop_constraint(
        op.f("fk_collections_owner_organization_id_organizations"),
        "collections",
        schema="corpus",
        type_="foreignkey",
    )
    op.drop_column("collections", "owner_organization_id", schema="corpus")
