"""Create admin-managed tax templates and taxability flags on tax_categories.

Tax setup moves from per-brand configuration to admin-owned, jurisdiction-
scoped templates (country → state → county → city, unset fields ignored).
At sale time the invoice engine resolves the rates for a site by matching
its location against active templates, so customers never configure tax.

This migration:
1. Creates tax_templates and tax_template_rates.
2. Adds is_system / is_tax_free flags to tax_categories so the two seeded
   taxability classes (Standard / Tax Free) are identifiable and protected.
3. Seeds country-level templates for the launch markets:
   AU → GST 10% inclusive, NZ → GST 15% inclusive.
4. Backfills every existing brand with the two system taxability categories.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create template tables, add taxability flags, seed AU/NZ, backfill brands."""
    op.create_table(
        "tax_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("county", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tax_templates_country", "tax_templates", ["country"])

    op.create_table(
        "tax_template_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tax_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tax_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rate_percent", sa.Numeric(10, 4), nullable=False),
        sa.Column("tax_model", sa.String(20), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tax_template_rates_tax_template_id", "tax_template_rates", ["tax_template_id"])

    # Taxability flags on the existing brand-scoped tax_categories table
    op.add_column(
        "tax_categories",
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "tax_categories",
        sa.Column("is_tax_free", sa.Boolean, nullable=False, server_default="false"),
    )

    # Seed launch-market templates: national GST, tax-inclusive pricing
    op.execute(
        "INSERT INTO tax_templates (id, name, country) VALUES "
        "(gen_random_uuid(), 'Australia GST', 'AU'), "
        "(gen_random_uuid(), 'New Zealand GST', 'NZ')"
    )
    op.execute(
        "INSERT INTO tax_template_rates (id, tax_template_id, name, rate_percent, tax_model) "
        "SELECT gen_random_uuid(), id, 'GST', 10.0000, 'inclusive' "
        "FROM tax_templates WHERE country = 'AU' AND name = 'Australia GST'"
    )
    op.execute(
        "INSERT INTO tax_template_rates (id, tax_template_id, name, rate_percent, tax_model) "
        "SELECT gen_random_uuid(), id, 'GST', 15.0000, 'inclusive' "
        "FROM tax_templates WHERE country = 'NZ' AND name = 'New Zealand GST'"
    )

    # Backfill the two system taxability classes for every existing brand
    op.execute(
        "INSERT INTO tax_categories (id, brand_id, name, is_active, is_system, is_tax_free) "
        "SELECT gen_random_uuid(), b.id, 'Standard', true, true, false FROM brands b "
        "WHERE NOT EXISTS (SELECT 1 FROM tax_categories tc WHERE tc.brand_id = b.id AND tc.name = 'Standard')"
    )
    op.execute(
        "INSERT INTO tax_categories (id, brand_id, name, is_active, is_system, is_tax_free) "
        "SELECT gen_random_uuid(), b.id, 'Tax Free', true, true, true FROM brands b "
        "WHERE NOT EXISTS (SELECT 1 FROM tax_categories tc WHERE tc.brand_id = b.id AND tc.name = 'Tax Free')"
    )


def downgrade() -> None:
    """Drop template tables and taxability flags (seeded categories are left in place)."""
    op.drop_column("tax_categories", "is_tax_free")
    op.drop_column("tax_categories", "is_system")
    op.drop_index("ix_tax_template_rates_tax_template_id", table_name="tax_template_rates")
    op.drop_table("tax_template_rates")
    op.drop_index("ix_tax_templates_country", table_name="tax_templates")
    op.drop_table("tax_templates")
