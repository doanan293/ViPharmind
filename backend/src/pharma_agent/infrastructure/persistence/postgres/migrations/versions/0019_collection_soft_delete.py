"""Collections are deleted softly; organizations no longer cascade into them.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-11 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="corpus",
    )
    op.drop_constraint(
        op.f("fk_collections_owner_organization_id_organizations"),
        "collections",
        schema="corpus",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM corpus.collections WHERE owner_organization_id IS NOT NULL"
        " AND owner_organization_id NOT IN (SELECT id FROM organizations)"
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
    op.drop_column("collections", "deleted_at", schema="corpus")
