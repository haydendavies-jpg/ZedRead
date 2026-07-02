"""Add address_city column to sites table.

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add address_city VARCHAR(100) with empty-string default (nullable=False)."""
    op.add_column(
        "sites",
        sa.Column("address_city", sa.String(100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Remove address_city from sites."""
    op.drop_column("sites", "address_city")
