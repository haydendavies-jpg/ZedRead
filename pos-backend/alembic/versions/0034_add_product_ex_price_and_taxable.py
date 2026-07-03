"""Add price_ex_cents and is_taxable to products.

Tax is no longer computed at sale time. Instead each product stores its
tax-INCLUSIVE price (base_price_cents, operator-entered) and a derived
tax-EXCLUSIVE price (price_ex_cents). A per-product is_taxable boolean
decides which is charged: taxable → inclusive (GST embedded), not taxable →
exclusive (no tax). price_ex_cents is derived from the brand's COUNTRY-level
inclusive tax rate when the product is saved.

Backfill for existing products:
1. is_taxable defaults to true; products whose tax category is Tax Free
   (is_tax_free) are set to false.
2. price_ex_cents is derived from base_price_cents using the combined
   country-level inclusive rate of the product's brand (0 where none exists,
   giving price_ex_cents == base_price_cents).

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the two columns and backfill from existing tax data."""
    op.add_column(
        "products",
        sa.Column("price_ex_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "products",
        sa.Column("is_taxable", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Products currently in a Tax Free category become non-taxable
    op.execute(
        "UPDATE products p SET is_taxable = false "
        "FROM tax_categories tc "
        "WHERE p.tax_category_id = tc.id AND tc.is_tax_free = true"
    )

    # Derive the tax-exclusive price from the brand's combined country-level
    # inclusive rate: ex = round(inc * 100 / (100 + rate)). Where a brand has
    # no matching country template the rate is 0 and ex == inc.
    op.execute(
        """
        UPDATE products p
        SET price_ex_cents = ROUND(
            p.base_price_cents * 100.0 / (100.0 + COALESCE(r.pct, 0))
        )
        FROM (
            SELECT b.id AS brand_id, COALESCE(SUM(tr.rate_percent), 0) AS pct
            FROM brands b
            LEFT JOIN tax_templates tt
                ON tt.country = b.country
                AND tt.is_active
                AND tt.state IS NULL AND tt.county IS NULL AND tt.city IS NULL
            LEFT JOIN tax_template_rates tr
                ON tr.tax_template_id = tt.id
                AND tr.is_active
                AND tr.tax_model = 'inclusive'
            GROUP BY b.id
        ) r
        WHERE p.brand_id = r.brand_id
        """
    )


def downgrade() -> None:
    """Drop the two product columns."""
    op.drop_column("products", "is_taxable")
    op.drop_column("products", "price_ex_cents")
