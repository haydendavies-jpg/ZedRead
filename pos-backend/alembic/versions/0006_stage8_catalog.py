"""Stage 8 catalog migration: extend categories, add tax_categories, tax_rates,
products, and site_product_overrides.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-05

Changes to existing tables:
  - categories: ADD tax_category_id, description, image_url, display_order, updated_at

New tables (in FK dependency order):
  1. tax_categories
  2. tax_rates             (depends on tax_categories)
  3. categories columns    (FK to tax_categories — added after table exists)
  4. products              (depends on brands, categories, tax_categories)
  5. site_product_overrides (depends on sites, products)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Stage 8 catalog tables and extend the categories table."""

    # 1. tax_categories — no FK deps beyond brands
    op.create_table(
        "tax_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
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
    op.create_index("ix_tax_categories_brand_id", "tax_categories", ["brand_id"])

    # 2. tax_rates — depends on tax_categories
    op.create_table(
        "tax_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tax_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        # NUMERIC(10, 4) — rule 9: never float for rates used in money calculations
        sa.Column("rate_percent", sa.Numeric(10, 4), nullable=False),
        sa.Column("tax_model", sa.String(20), nullable=False),
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
    op.create_index("ix_tax_rates_tax_category_id", "tax_rates", ["tax_category_id"])

    # 3. Extend categories with Stage 8 columns
    # tax_category_id added after tax_categories table exists
    op.add_column(
        "categories",
        sa.Column(
            "tax_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "categories",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "categories",
        sa.Column("image_url", sa.String(1024), nullable=True),
    )
    op.add_column(
        "categories",
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "categories",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 4. products — depends on brands, categories, tax_categories
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "tax_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # BIGINT cents — rule 4 + 9
        sa.Column("base_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("photo_url", sa.String(1024), nullable=True),
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
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_category_id", "products", ["category_id"])

    # 5. site_product_overrides — depends on sites, products
    op.create_table(
        "site_product_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
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
    op.create_index("ix_site_product_overrides_site_id", "site_product_overrides", ["site_id"])
    op.create_index(
        "ix_site_product_overrides_product_id", "site_product_overrides", ["product_id"]
    )
    # Unique constraint: only one override row per product per site
    op.create_unique_constraint(
        "uq_site_product_overrides_site_product",
        "site_product_overrides",
        ["site_id", "product_id"],
    )


def downgrade() -> None:
    """Reverse Stage 8: drop tables and revert categories columns."""
    op.drop_table("site_product_overrides")
    op.drop_table("products")
    op.drop_column("categories", "updated_at")
    op.drop_column("categories", "display_order")
    op.drop_column("categories", "image_url")
    op.drop_column("categories", "description")
    op.drop_column("categories", "tax_category_id")
    op.drop_table("tax_rates")
    op.drop_table("tax_categories")
