"""Add addressable grid position to menu_buttons (POS Layout drag-to-any-cell).

The grid editor's width/height + display_order fields only supported
sequential dense-pack layout (grid-auto-flow: dense computing position from
span+order) — there was no way to address an arbitrary, possibly-empty grid
cell. This adds grid_col/grid_row so a button can be pinned to an explicit
cell; both stay nullable so existing (and freshly-created) buttons keep
falling back to the dense-pack ordering until the user actually drags them.

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable grid_col/grid_row columns to menu_buttons."""
    op.add_column(
        "menu_buttons",
        sa.Column(
            "grid_col",
            sa.Integer(),
            nullable=True,
            comment="0-indexed column of the button's top-left cell (0-5 in the 6-column grid); NULL means auto-packed via display_order",
        ),
    )
    op.add_column(
        "menu_buttons",
        sa.Column(
            "grid_row",
            sa.Integer(),
            nullable=True,
            comment="0-indexed row of the button's top-left cell; NULL means auto-packed via display_order",
        ),
    )
    # Mirror the existing width/height range checks — bound grid_col to the
    # 6-column grid. grid_row is intentionally left unbounded (rows grow
    # downward without a fixed limit).
    op.create_check_constraint(
        "ck_menu_buttons_grid_col_range",
        "menu_buttons",
        "grid_col IS NULL OR grid_col BETWEEN 0 AND 5",
    )
    op.create_check_constraint(
        "ck_menu_buttons_grid_row_range",
        "menu_buttons",
        "grid_row IS NULL OR grid_row >= 0",
    )


def downgrade() -> None:
    """Drop the grid position columns and their check constraints."""
    op.drop_constraint("ck_menu_buttons_grid_row_range", "menu_buttons", type_="check")
    op.drop_constraint("ck_menu_buttons_grid_col_range", "menu_buttons", type_="check")
    op.drop_column("menu_buttons", "grid_row")
    op.drop_column("menu_buttons", "grid_col")
