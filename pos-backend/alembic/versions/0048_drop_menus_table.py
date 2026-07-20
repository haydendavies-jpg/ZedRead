"""Drop the menus table and its ref sequence.

The `Menus` screen (migration `0041`) was a saved, schedulable configuration
distinct from a `menu_layouts` row, but nothing ever consumed it: the POS
read contract (`GET /pos/menu-layout`) only ever read `menu_layouts`, and
Phase 2 (migration `0042`) added the same draft/schedule/publish lifecycle
directly onto `menu_layouts` (`is_published`, `published_at`,
`scheduled_publish_at`), which Menu Studio's POS Layout editor already
surfaces. The Menus tab duplicated that lifecycle without ever feeding the
thing it claimed to configure, so the entity, its route/service/schema, and
the nav tab are removed as redundant.

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the menus table and its ref sequence."""
    op.drop_index("ix_menus_site_id", table_name="menus")
    op.drop_index("ix_menus_brand_id", table_name="menus")
    op.drop_table("menus")
    op.execute("DROP SEQUENCE IF EXISTS menus_ref_seq")


def downgrade() -> None:
    """Recreate the menus table and its ref sequence."""
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
