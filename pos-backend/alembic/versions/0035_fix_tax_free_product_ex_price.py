"""Fix price_ex_cents for tax-free products incorrectly rate-stripped by 0034.

Migration 0034's backfill derived every product's price_ex_cents from the
brand's country inclusive rate, without checking is_taxable. That's correct
for taxable products (GST embedded, must be stripped out) but wrong for
tax-free products — there is no tax to strip, so the exclusive price (what
is actually charged at sale, per invoice_service) should equal the entered
price exactly. The same gap existed in product_service.create/update_product
until this change; both are now fixed at the code layer too.

This migration corrects existing data: any product with is_taxable = false
gets price_ex_cents reset to base_price_cents.

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-04
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reset price_ex_cents = base_price_cents for every tax-free product."""
    op.execute(
        "UPDATE products SET price_ex_cents = base_price_cents WHERE is_taxable = false"
    )


def downgrade() -> None:
    """No-op — the pre-fix values were wrong and are not worth restoring."""
    pass
