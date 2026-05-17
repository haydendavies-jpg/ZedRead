"""Stage 9 variant tables: product_attribute_types, product_attribute_values,
product_variants, product_variant_attributes (composite PK), site_variant_overrides.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 5 Stage 9 variant tables in FK dependency order."""

    # 1. product_attribute_types — depends on brands
    op.create_table(
        "product_attribute_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_product_attribute_types_brand_id", "product_attribute_types", ["brand_id"])

    # 2. product_attribute_values — depends on product_attribute_types
    op.create_table(
        "product_attribute_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attribute_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_attribute_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_product_attribute_values_type_id", "product_attribute_values", ["attribute_type_id"]
    )

    # 3. product_variants — depends on products
    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
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
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    # 4. product_variant_attributes — composite PK enforces one value per type per variant
    op.create_table(
        "product_variant_attributes",
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attribute_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_attribute_types.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attribute_value_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_attribute_values.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("variant_id", "attribute_type_id", name="pk_product_variant_attributes"),
    )

    # 5. site_variant_overrides — depends on sites, product_variants
    op.create_table(
        "site_variant_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("override_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
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
    op.create_index("ix_site_variant_overrides_site_id", "site_variant_overrides", ["site_id"])
    op.create_index("ix_site_variant_overrides_variant_id", "site_variant_overrides", ["variant_id"])
    op.create_unique_constraint(
        "uq_site_variant_overrides_site_variant",
        "site_variant_overrides",
        ["site_id", "variant_id"],
    )


def downgrade() -> None:
    """Drop all 5 Stage 9 variant tables in reverse dependency order."""
    op.drop_table("site_variant_overrides")
    op.drop_table("product_variant_attributes")
    op.drop_table("product_variants")
    op.drop_table("product_attribute_values")
    op.drop_table("product_attribute_types")
