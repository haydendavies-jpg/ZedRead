"""Table maps & floor service (Android POS Phase 4).

Adds the authoring layer (table_maps / table_map_shapes, reusing the
Menu Studio POS Layout editor's shape/publish architecture) and the live
occupancy layer (dining_tables / table_sessions) described in
ANDROID_POS_BUILD_PLAN.md's "Phase 4 — Table maps & floor service" and
design_handoff_zedread/README-tables-floormap.md.

dining_tables.active_session_id and table_sessions.merge_partner_session_id
are a circular FK pair (each table names the other) — both are added with
use_alter=True and created via separate ALTER TABLE ... ADD CONSTRAINT calls
after both tables exist, the standard pattern for a mutual FK cycle.

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create table_maps, table_map_shapes, dining_tables, and table_sessions."""
    op.create_table(
        "table_maps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grid_size", sa.Integer, nullable=False, server_default="20"),
        sa.Column("is_grid_locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_table_maps_brand_id", "table_maps", ["brand_id"])
    op.create_index("ix_table_maps_site_id", "table_maps", ["site_id"])

    op.create_table(
        "table_map_shapes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("table_map_id", UUID(as_uuid=True), sa.ForeignKey("table_maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("x", sa.Float, nullable=False),
        sa.Column("y", sa.Float, nullable=False),
        sa.Column("w", sa.Float, nullable=False),
        sa.Column("h", sa.Float, nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("is_locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("dashed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('bar_counter', 'entrance', 'rect', 'round', 'stool', 'wall', 'zone')",
            name="ck_table_map_shapes_kind_valid",
        ),
    )
    op.create_index("ix_table_map_shapes_table_map_id", "table_map_shapes", ["table_map_id"])

    op.create_table(
        "table_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # dining_table_id's FK is added below via a separate ALTER, once dining_tables exists
        sa.Column("dining_table_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="seated"),
        sa.Column("covers", sa.BigInteger, nullable=False),
        sa.Column("seated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_touch_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("server_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("merge_partner_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_ref", sa.String(64), nullable=True, unique=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('bill', 'ordered', 'seated')", name="ck_table_sessions_status_valid"),
    )
    op.create_index("ix_table_sessions_dining_table_id", "table_sessions", ["dining_table_id"])

    op.create_table(
        "dining_tables",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "table_map_shape_id",
            UUID(as_uuid=True),
            sa.ForeignKey("table_map_shapes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_label", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dining_tables_table_map_shape_id", "dining_tables", ["table_map_shape_id"])
    op.create_index("ix_dining_tables_site_id", "dining_tables", ["site_id"])
    op.create_index("ix_dining_tables_active_session_id", "dining_tables", ["active_session_id"])

    # Close the circular FK pair now both tables exist.
    op.create_foreign_key(
        "fk_table_sessions_dining_table_id", "table_sessions", "dining_tables", ["dining_table_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_table_sessions_merge_partner_session_id",
        "table_sessions",
        "table_sessions",
        ["merge_partner_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_dining_tables_active_session_id", "dining_tables", "table_sessions", ["active_session_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Drop dining_tables, table_sessions, table_map_shapes, and table_maps."""
    op.drop_constraint("fk_dining_tables_active_session_id", "dining_tables", type_="foreignkey")
    op.drop_constraint("fk_table_sessions_merge_partner_session_id", "table_sessions", type_="foreignkey")
    op.drop_constraint("fk_table_sessions_dining_table_id", "table_sessions", type_="foreignkey")

    op.drop_index("ix_dining_tables_active_session_id", table_name="dining_tables")
    op.drop_index("ix_dining_tables_site_id", table_name="dining_tables")
    op.drop_index("ix_dining_tables_table_map_shape_id", table_name="dining_tables")
    op.drop_table("dining_tables")

    op.drop_index("ix_table_sessions_dining_table_id", table_name="table_sessions")
    op.drop_table("table_sessions")

    op.drop_index("ix_table_map_shapes_table_map_id", table_name="table_map_shapes")
    op.drop_table("table_map_shapes")

    op.drop_index("ix_table_maps_site_id", table_name="table_maps")
    op.drop_index("ix_table_maps_brand_id", table_name="table_maps")
    op.drop_table("table_maps")
