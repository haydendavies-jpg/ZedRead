"""Human-readable invoice reference — invoices.ref.

Every other major entity (Product, Category, ReportingGroup, Variant, Combo,
formerly Menus) already carries an INV-000001-style ref sequence; Invoice
never did, leaving only the raw UUID id as an "invoice number" — flagged in
user testing of the Android Register's Invoice Search screen, which needs
something a cashier can actually search by. Same mechanism as migration
0039's product_variants_ref_seq / product_combo_groups_ref_seq.

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add invoices.ref, backed by a new sequence, not null and unique."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS invoices_ref_seq START 1 INCREMENT 1")
    op.add_column(
        "invoices",
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'INV-' || LPAD(nextval('invoices_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. INV-000001",
        ),
    )


def downgrade() -> None:
    """Drop invoices.ref and its backing sequence."""
    op.drop_column("invoices", "ref")
    op.execute("DROP SEQUENCE IF EXISTS invoices_ref_seq")
