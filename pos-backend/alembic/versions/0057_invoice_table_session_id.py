"""Invoice table-session handoff — invoices.table_session_id (Android POS Phase 4).

Lets the Tables screen's "Open order →" action attach a Register order to
the table's open occupancy session. Nullable — counter-service sales with
no table context are unaffected.

Revision ID: 0057
Revises: 0056
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add invoices.table_session_id, nullable FK to table_sessions."""
    op.add_column(
        "invoices",
        sa.Column(
            "table_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("table_sessions.id", ondelete="SET NULL"),
            nullable=True,
            comment="The table occupancy this order is attached to — NULL for counter-service sales",
        ),
    )
    op.create_index("ix_invoices_table_session_id", "invoices", ["table_session_id"])


def downgrade() -> None:
    """Drop invoices.table_session_id."""
    op.drop_index("ix_invoices_table_session_id", table_name="invoices")
    op.drop_column("invoices", "table_session_id")
