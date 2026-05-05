"""Stage 11: create 8 reporting views over the invoice engine tables.

Views are NOT detected by Alembic autogenerate — this migration is hand-written
using op.execute() per the Stage 11 plan requirement.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-05
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


# ── View DDL ─────────────────────────────────────────────────────────────────

_VIEWS = [
    # 1. Daily sales totals per site
    (
        "vw_daily_sales",
        """
        CREATE VIEW vw_daily_sales AS
        SELECT
            i.brand_id,
            i.site_id,
            DATE(i.created_at) AS sale_date,
            COUNT(*) AS invoice_count,
            COALESCE(SUM(i.subtotal_cents), 0) AS subtotal_cents,
            COALESCE(SUM(i.tax_cents), 0) AS tax_cents,
            COALESCE(SUM(i.discount_cents), 0) AS discount_cents,
            COALESCE(SUM(i.total_cents), 0) AS total_cents
        FROM invoices i
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY i.brand_id, i.site_id, DATE(i.created_at)
        """,
    ),
    # 2. Product revenue from paid sale line items
    (
        "vw_product_revenue",
        """
        CREATE VIEW vw_product_revenue AS
        SELECT
            ili.product_id,
            ili.product_name,
            i.brand_id,
            i.site_id,
            SUM(ili.quantity) AS total_units,
            COALESCE(SUM(ili.subtotal_cents), 0) AS revenue_cents,
            COALESCE(SUM(ili.tax_cents), 0) AS tax_cents
        FROM invoice_line_items ili
        JOIN invoices i ON ili.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY ili.product_id, ili.product_name, i.brand_id, i.site_id
        """,
    ),
    # 3. Payment method breakdown per site
    (
        "vw_payment_methods",
        """
        CREATE VIEW vw_payment_methods AS
        SELECT
            p.method,
            i.brand_id,
            i.site_id,
            COUNT(*) AS payment_count,
            COALESCE(SUM(p.amount_cents), 0) AS total_amount_cents
        FROM payments p
        JOIN invoices i ON p.invoice_id = i.id
        WHERE i.invoice_type = 'sale'
        GROUP BY p.method, i.brand_id, i.site_id
        """,
    ),
    # 4. Tax collected by rate name per site
    (
        "vw_tax_collected",
        """
        CREATE VIEW vw_tax_collected AS
        SELECT
            itb.tax_rate_name,
            itb.rate_percent,
            itb.tax_model,
            i.brand_id,
            i.site_id,
            COALESCE(SUM(itb.taxable_amount_cents), 0) AS taxable_amount_cents,
            COALESCE(SUM(itb.tax_amount_cents), 0) AS tax_amount_cents
        FROM invoice_tax_breakdowns itb
        JOIN invoices i ON itb.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY itb.tax_rate_name, itb.rate_percent, itb.tax_model, i.brand_id, i.site_id
        """,
    ),
    # 5. Hourly sales pattern per site
    (
        "vw_hourly_sales",
        """
        CREATE VIEW vw_hourly_sales AS
        SELECT
            i.brand_id,
            i.site_id,
            EXTRACT(HOUR FROM i.created_at)::INTEGER AS hour_of_day,
            COUNT(*) AS invoice_count,
            COALESCE(SUM(i.total_cents), 0) AS total_cents
        FROM invoices i
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY i.brand_id, i.site_id, EXTRACT(HOUR FROM i.created_at)
        """,
    ),
    # 6. Modifier usage popularity per brand
    (
        "vw_modifier_popularity",
        """
        CREATE VIEW vw_modifier_popularity AS
        SELECT
            ilm.modifier_name,
            i.brand_id,
            COUNT(*) AS usage_count,
            COALESCE(SUM(ilm.price_delta_cents), 0) AS total_revenue_impact_cents
        FROM invoice_line_modifiers ilm
        JOIN invoice_line_items ili ON ilm.line_item_id = ili.id
        JOIN invoices i ON ili.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY ilm.modifier_name, i.brand_id
        """,
    ),
    # 7. Invoice detail with joined site and brand names
    (
        "vw_invoice_detail",
        """
        CREATE VIEW vw_invoice_detail AS
        SELECT
            i.id,
            i.brand_id,
            i.site_id,
            i.created_by_id,
            i.invoice_type,
            i.status,
            i.subtotal_cents,
            i.tax_cents,
            i.discount_cents,
            i.total_cents,
            i.refund_of_id,
            i.is_refunded,
            i.voided_at,
            i.paid_at,
            i.created_at,
            s.name AS site_name,
            b.name AS brand_name
        FROM invoices i
        JOIN sites s ON i.site_id = s.id
        JOIN brands b ON i.brand_id = b.id
        """,
    ),
    # 8. Daily refund summary per site
    (
        "vw_refund_summary",
        """
        CREATE VIEW vw_refund_summary AS
        SELECT
            i.brand_id,
            i.site_id,
            DATE(i.created_at) AS refund_date,
            COUNT(*) AS refund_count,
            COALESCE(SUM(ABS(i.total_cents)), 0) AS refund_total_cents
        FROM invoices i
        WHERE i.invoice_type = 'refund'
        GROUP BY i.brand_id, i.site_id, DATE(i.created_at)
        """,
    ),
]


def upgrade() -> None:
    """Create all 8 reporting views using raw SQL (autogenerate cannot detect views)."""
    for _name, sql in _VIEWS:
        op.execute(sql.strip())


def downgrade() -> None:
    """Drop all 8 reporting views in reverse dependency order."""
    for name, _sql in reversed(_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {name}")
