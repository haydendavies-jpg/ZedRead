"""Drop site product/variant override tables (feature descoped).

The per-site price/availability override feature (site_product_overrides and
site_variant_overrides) is being removed — it was never right in
implementation and will be rescoped later. This migration drops both tables
and their indexes/constraints. The downgrade recreates them empty, matching
their original definitions in migrations 0006 (products) and 0007 (variants).

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop both site override tables (indexes/constraints drop with them)."""
    # Variant-level overrides depended on product_variants; drop it first, though
    # either order is safe as neither table is referenced by another table.
    op.drop_table("site_variant_overrides")
    op.drop_table("site_product_overrides")


def downgrade() -> None:
    """Recreate both override tables empty, matching their original schema."""
    # site_product_overrides — originally created in migration 0006.
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
    op.create_unique_constraint(
        "uq_site_product_overrides_site_product",
        "site_product_overrides",
        ["site_id", "product_id"],
    )

    # site_variant_overrides — originally created in migration 0007.
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
