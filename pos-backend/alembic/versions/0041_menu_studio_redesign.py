"""Menu Studio redesign: category default colour, modifier comboing (linked
groups), and the Menus entity (distinct from a POS menu layout).

- categories.default_color — the POS button colour a category's products
  default to on a POS layout, unless a button has its own override.
- modifier_option_group_links — a many-to-many "comboing" link from a
  ModifierOption to another ModifierGroup it expands into (the inline nested
  cascade in the portal's Modifiers tab). Self-referential through
  modifier_groups; the API only ever serialises one level deep today, but
  nothing here prevents a linked group's own options from also carrying
  links, so deeper nesting is possible later without another migration.
- menus / menus_ref_seq — a saved, schedulable configuration distinct from a
  MenuLayout (the button arrangement). Reuses the brand/site "scope" pattern
  already established by menu_layouts so a menu can be assigned brand-wide or
  to a single site (the closest existing stand-in for a POS "register" /
  "channel" — no such entity exists yet).

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add category colour, modifier option→group links, and the menus table."""
    op.add_column(
        "categories",
        sa.Column(
            "default_color",
            sa.String(7),
            nullable=False,
            server_default="#5A5550",
            comment="Hex colour (#RRGGBB) POS layout buttons default to for this category's products",
        ),
    )

    op.create_table(
        "modifier_option_group_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "modifier_option_id",
            UUID(as_uuid=True),
            sa.ForeignKey("modifier_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "linked_group_id",
            UUID(as_uuid=True),
            sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_modifier_option_group_links_option_id",
        "modifier_option_group_links",
        ["modifier_option_id"],
    )
    op.create_unique_constraint(
        "uq_modifier_option_group_links_option_group",
        "modifier_option_group_links",
        ["modifier_option_id", "linked_group_id"],
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS menus_ref_seq START 1 INCREMENT 1")

    op.create_table(
        "menus",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'MNU-' || LPAD(nextval('menus_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. MNU-000001",
        ),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope", sa.String(10), nullable=False, comment="'brand' (all sites) or 'site' (this site_id only)"),
        sa.Column("menu_layout_id", UUID(as_uuid=True), sa.ForeignKey("menu_layouts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft", comment="'draft' | 'scheduled' | 'published'"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(scope = 'site' AND site_id IS NOT NULL) OR (scope = 'brand' AND site_id IS NULL)",
            name="ck_menus_scope_site_consistency",
        ),
        sa.CheckConstraint("status IN ('draft', 'scheduled', 'published')", name="ck_menus_status_valid"),
    )
    op.create_index("ix_menus_brand_id", "menus", ["brand_id"])
    op.create_index("ix_menus_site_id", "menus", ["site_id"])


def downgrade() -> None:
    """Drop the menus table, modifier comboing links, and category colour column."""
    op.drop_index("ix_menus_site_id", table_name="menus")
    op.drop_index("ix_menus_brand_id", table_name="menus")
    op.drop_table("menus")
    op.execute("DROP SEQUENCE IF EXISTS menus_ref_seq")

    op.drop_constraint(
        "uq_modifier_option_group_links_option_group",
        "modifier_option_group_links",
        type_="unique",
    )
    op.drop_index("ix_modifier_option_group_links_option_id", table_name="modifier_option_group_links")
    op.drop_table("modifier_option_group_links")

    op.drop_column("categories", "default_color")
