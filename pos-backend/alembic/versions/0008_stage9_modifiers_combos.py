"""Stage 9 modifier and combo tables: modifier_groups, modifier_options,
product_modifier_group_links, product_combo_groups, product_combo_options.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 5 modifier/combo tables in FK dependency order."""

    # 1. modifier_groups — depends on brands
    op.create_table(
        "modifier_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("min_selections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_selections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_modifier_groups_brand_id", "modifier_groups", ["brand_id"])

    # 2. modifier_options — depends on modifier_groups
    op.create_table(
        "modifier_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "modifier_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("price_delta_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_modifier_options_group_id", "modifier_options", ["modifier_group_id"]
    )

    # 3. product_modifier_group_links — depends on products, modifier_groups
    op.create_table(
        "product_modifier_group_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modifier_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_product_modifier_group_links_product_id", "product_modifier_group_links", ["product_id"]
    )

    # 4. product_combo_groups — depends on products
    op.create_table(
        "product_combo_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("min_selections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_selections", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_product_combo_groups_product_id", "product_combo_groups", ["product_id"]
    )

    # 5. product_combo_options — depends on product_combo_groups, products
    op.create_table(
        "product_combo_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "combo_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_combo_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price_delta_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_product_combo_options_combo_group_id", "product_combo_options", ["combo_group_id"]
    )


def downgrade() -> None:
    """Drop all 5 modifier/combo tables in reverse dependency order."""
    op.drop_table("product_combo_options")
    op.drop_table("product_combo_groups")
    op.drop_table("product_modifier_group_links")
    op.drop_table("modifier_options")
    op.drop_table("modifier_groups")
