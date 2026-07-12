"""Stage 23 — POS Menu Builder: menu_layouts, menu_tabs, menu_buttons.

Prototype scope: single-level tabs + buttons only, no nested sub-menus.
menu_buttons.product_ref stores a product's human-readable ref code
(e.g. PRD-000001) rather than a product FK, so a button keeps working if the
underlying product is deleted and recreated with the same code — per the
original ask ("purely graphical... relate back to the product based on
product code").

More than one menu_layout can have is_published=True at once (e.g. per-site
or day-part menus), matching the "more than one selectable" requirement.

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create menu_layouts, menu_tabs, and menu_buttons tables."""
    op.create_table(
        "menu_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=True,
            comment="Set only when scope='site' — a site-specific menu layout",
        ),
        sa.Column(
            "scope",
            sa.String(10),
            nullable=False,
            comment="'brand' (all sites) or 'site' (this site_id only)",
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="More than one layout may be published at once (per-site/day-part menus)",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Incremented each time the layout is published",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(scope = 'site' AND site_id IS NOT NULL) OR (scope = 'brand' AND site_id IS NULL)",
            name="ck_menu_layouts_scope_site_consistency",
        ),
    )
    op.create_index("ix_menu_layouts_brand_id", "menu_layouts", ["brand_id"])
    op.create_index("ix_menu_layouts_site_id", "menu_layouts", ["site_id"])

    op.create_table(
        "menu_tabs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "layout_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_menu_tabs_layout_id", "menu_tabs", ["layout_id"])

    op.create_table(
        "menu_buttons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tab_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_tabs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_ref",
            sa.String(20),
            nullable=False,
            comment="Product's ref code (e.g. PRD-000001) — deliberately not a FK, per the stage plan",
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_menu_buttons_tab_id", "menu_buttons", ["tab_id"])


def downgrade() -> None:
    """Drop menu_buttons, menu_tabs, and menu_layouts in FK-safe order."""
    op.drop_index("ix_menu_buttons_tab_id", table_name="menu_buttons")
    op.drop_table("menu_buttons")

    op.drop_index("ix_menu_tabs_layout_id", table_name="menu_tabs")
    op.drop_table("menu_tabs")

    op.drop_index("ix_menu_layouts_site_id", table_name="menu_layouts")
    op.drop_index("ix_menu_layouts_brand_id", table_name="menu_layouts")
    op.drop_table("menu_layouts")
