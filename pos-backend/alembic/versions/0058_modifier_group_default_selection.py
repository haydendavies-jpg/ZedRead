"""Modifier group default-selection flag — modifier_groups.is_first_option_default_selected.

User-testing feedback: the Android Register's customise sheet pre-selected a
single-select group's first option automatically, which testers didn't want
— nothing should be pre-selected unless a manager explicitly opts a group
into that behaviour from Menu Studio's Modifiers tab. Defaults False for
every existing group, which is itself a behaviour change from before this
migration (groups used to always default-select) — deliberate, per the
feedback.

Revision ID: 0058
Revises: 0057
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add modifier_groups.is_first_option_default_selected, not null, defaulting False."""
    op.add_column(
        "modifier_groups",
        sa.Column(
            "is_first_option_default_selected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="True — the POS pre-selects this group's first option when the customise sheet opens.",
        ),
    )


def downgrade() -> None:
    """Drop modifier_groups.is_first_option_default_selected."""
    op.drop_column("modifier_groups", "is_first_option_default_selected")
