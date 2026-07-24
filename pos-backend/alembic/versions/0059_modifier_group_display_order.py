"""Modifier group display order — modifier_groups.display_order.

Management Portal tweaks: the Modifiers tab lists groups alphabetically by
name with no way to control the order the POS presents them in. Adds a
display_order column (mirroring modifier_options.display_order and
product_modifier_group_links.display_order) so the groups themselves can be
drag-reordered; a product's own product_modifier_group_links.display_order
(Stage 23's per-product reorder) already takes precedence for that product
when set, unchanged by this migration.

Revision ID: 0059
Revises: 0058
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add modifier_groups.display_order, not null, defaulting 0."""
    op.add_column(
        "modifier_groups",
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Order groups appear in on the POS and the Modifiers tab — lower values first.",
        ),
    )


def downgrade() -> None:
    """Drop modifier_groups.display_order."""
    op.drop_column("modifier_groups", "display_order")
