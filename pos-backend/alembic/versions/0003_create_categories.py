"""create categories table (Stage 3 stub — extended in Stage 8)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the categories table with the minimal Stage 3 column set.

    Stage 8 will ADD columns to this table without removing any defined here.
    Never remove or rename columns from this migration.
    """
    op.create_table(
        "categories",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_categories_brand_id", "categories", ["brand_id"])


def downgrade() -> None:
    """Drop the categories table."""
    op.drop_index("ix_categories_brand_id", table_name="categories")
    op.drop_table("categories")
