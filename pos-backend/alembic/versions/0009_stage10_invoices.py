"""Stage 10 invoice tables: invoices, invoice_line_items, invoice_line_modifiers,
invoice_tax_breakdowns, payments.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 5 invoice tables in FK dependency order."""

    # 1. invoices — depends on brands, sites, pos_users
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pos_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("invoice_type", sa.String(20), nullable=False, server_default="sale"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("discount_reason", sa.String(255), nullable=True),
        sa.Column("total_cents", sa.BigInteger(), nullable=False, server_default="0"),
        # Self-referential FK — added after table creation (see below)
        sa.Column("refund_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_refunded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
    # Self-referential FK: added after the table exists
    op.create_foreign_key(
        "fk_invoices_refund_of_id",
        "invoices",
        "invoices",
        ["refund_of_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_invoices_brand_id", "invoices", ["brand_id"])
    op.create_index("ix_invoices_site_id", "invoices", ["site_id"])

    # 2. invoice_line_items — depends on invoices, products
    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # SNAPSHOT fields — never update after creation
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("unit_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_category_name", sa.String(100), nullable=True),
        sa.Column(
            "tax_rate_percent",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("tax_model", sa.String(20), nullable=False, server_default="exclusive"),
        # Computed quantities
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("line_total_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_invoice_line_items_invoice_id", "invoice_line_items", ["invoice_id"])

    # 3. invoice_line_modifiers — depends on invoice_line_items, modifier_options
    op.create_table(
        "invoice_line_modifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "line_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoice_line_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modifier_option_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier_options.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # SNAPSHOT fields
        sa.Column("modifier_name", sa.String(100), nullable=False),
        sa.Column("price_delta_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_invoice_line_modifiers_line_item_id", "invoice_line_modifiers", ["line_item_id"]
    )

    # 4. invoice_tax_breakdowns — depends on invoices, tax_rates
    op.create_table(
        "invoice_tax_breakdowns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tax_rate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_rates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # SNAPSHOT fields
        sa.Column("tax_rate_name", sa.String(100), nullable=False),
        sa.Column("rate_percent", sa.Numeric(10, 4), nullable=False),
        sa.Column("tax_model", sa.String(20), nullable=False),
        # Computed totals
        sa.Column("taxable_amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tax_amount_cents", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_invoice_tax_breakdowns_invoice_id", "invoice_tax_breakdowns", ["invoice_id"]
    )

    # 5. payments — depends on invoices
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])


def downgrade() -> None:
    """Drop all 5 invoice tables in reverse dependency order."""
    op.drop_table("payments")
    op.drop_table("invoice_tax_breakdowns")
    op.drop_table("invoice_line_modifiers")
    op.drop_table("invoice_line_items")
    op.drop_constraint("fk_invoices_refund_of_id", "invoices", type_="foreignkey")
    op.drop_table("invoices")
