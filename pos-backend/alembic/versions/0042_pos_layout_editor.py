"""POS Layout grid editor redesign (Menu Studio Phase 2).

Adds what the Stage 23 prototype schema didn't need yet:
- menu_layouts: a display colour, active-time/day-of-week scheduling (when
  the layout is visible on the POS, distinct from is_published — "when the
  edits go live"), a scheduled_publish_at for the "Schedule publish" bulk
  action, and published_at (the list view's "Last published" column had
  nothing to read before this).
- menu_tabs: self-referential nesting (parent_tab_id) so a tab can drill into
  a tab-inside-a-tab, and its own display colour (rail dot / folder tile
  accent).
- menu_buttons: `kind` ('product' | 'folder') — a folder button represents a
  nested tab instead of a product; product_ref becomes nullable to make room
  for that. width/height (grid cell span, CSS grid-auto-flow:dense packs
  around them — no x/y coordinates needed) and an optional colour override
  (falls back to the linked product's category default colour when unset).

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add layout scheduling/colour, nested tabs, and rich (kind/span/colour) buttons."""
    op.add_column("menu_layouts", sa.Column("color", sa.String(7), nullable=False, server_default="#A82040"))
    op.add_column("menu_layouts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("menu_layouts", sa.Column("is_all_day", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("menu_layouts", sa.Column("start_time", sa.Time, nullable=True))
    op.add_column("menu_layouts", sa.Column("end_time", sa.Time, nullable=True))
    op.add_column(
        "menu_layouts",
        sa.Column(
            "active_days",
            sa.ARRAY(sa.SmallInteger),
            nullable=False,
            server_default="{0,1,2,3,4,5,6}",
            comment="Weekdays the layout is visible on the POS — 0=Monday .. 6=Sunday (date.weekday() convention)",
        ),
    )
    op.add_column("menu_layouts", sa.Column("scheduled_publish_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "menu_tabs",
        sa.Column("parent_tab_id", UUID(as_uuid=True), sa.ForeignKey("menu_tabs.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column("menu_tabs", sa.Column("color", sa.String(7), nullable=True))
    op.create_index("ix_menu_tabs_parent_tab_id", "menu_tabs", ["parent_tab_id"])

    op.add_column("menu_buttons", sa.Column("kind", sa.String(10), nullable=False, server_default="product"))
    op.alter_column("menu_buttons", "product_ref", existing_type=sa.String(20), nullable=True)
    op.add_column(
        "menu_buttons",
        sa.Column("child_tab_id", UUID(as_uuid=True), sa.ForeignKey("menu_tabs.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("menu_buttons", sa.Column("width", sa.Integer, nullable=False, server_default="1"))
    op.add_column("menu_buttons", sa.Column("height", sa.Integer, nullable=False, server_default="1"))
    op.add_column("menu_buttons", sa.Column("color", sa.String(7), nullable=True))
    op.create_index("ix_menu_buttons_child_tab_id", "menu_buttons", ["child_tab_id"])
    op.create_check_constraint("ck_menu_buttons_kind_valid", "menu_buttons", "kind IN ('product', 'folder')")
    op.create_check_constraint("ck_menu_buttons_width_range", "menu_buttons", "width BETWEEN 1 AND 6")
    op.create_check_constraint("ck_menu_buttons_height_range", "menu_buttons", "height BETWEEN 1 AND 4")
    op.create_check_constraint(
        "ck_menu_buttons_kind_fields_consistency",
        "menu_buttons",
        "(kind = 'product' AND product_ref IS NOT NULL AND child_tab_id IS NULL) OR "
        "(kind = 'folder' AND child_tab_id IS NOT NULL AND product_ref IS NULL)",
    )


def downgrade() -> None:
    """Drop the POS Layout editor's scheduling, nesting, and rich-button columns."""
    op.drop_constraint("ck_menu_buttons_kind_fields_consistency", "menu_buttons", type_="check")
    op.drop_constraint("ck_menu_buttons_height_range", "menu_buttons", type_="check")
    op.drop_constraint("ck_menu_buttons_width_range", "menu_buttons", type_="check")
    op.drop_constraint("ck_menu_buttons_kind_valid", "menu_buttons", type_="check")
    op.drop_index("ix_menu_buttons_child_tab_id", table_name="menu_buttons")
    op.drop_column("menu_buttons", "color")
    op.drop_column("menu_buttons", "height")
    op.drop_column("menu_buttons", "width")
    op.drop_column("menu_buttons", "child_tab_id")
    op.alter_column("menu_buttons", "product_ref", existing_type=sa.String(20), nullable=False)
    op.drop_column("menu_buttons", "kind")

    op.drop_index("ix_menu_tabs_parent_tab_id", table_name="menu_tabs")
    op.drop_column("menu_tabs", "color")
    op.drop_column("menu_tabs", "parent_tab_id")

    op.drop_column("menu_layouts", "scheduled_publish_at")
    op.drop_column("menu_layouts", "active_days")
    op.drop_column("menu_layouts", "end_time")
    op.drop_column("menu_layouts", "start_time")
    op.drop_column("menu_layouts", "is_all_day")
    op.drop_column("menu_layouts", "published_at")
    op.drop_column("menu_layouts", "color")
