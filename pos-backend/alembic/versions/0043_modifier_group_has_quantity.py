"""Add has_quantity to modifier_groups (Menu Studio feedback).

When true, the POS lets the cashier select the same option more than once
(a per-option quantity), with the total count still capped by the group's
max_selections. When false (the default, matching all pre-existing groups),
each option can be chosen at most once.

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the has_quantity flag, defaulting existing groups to the old once-per-option behaviour."""
    op.add_column(
        "modifier_groups",
        sa.Column(
            "has_quantity",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="True — the same option may be selected multiple times (per-option quantity), up to max_selections total",
        ),
    )


def downgrade() -> None:
    """Drop the has_quantity flag."""
    op.drop_column("modifier_groups", "has_quantity")
