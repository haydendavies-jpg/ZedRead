"""Stage 16 — Reporting Groups: brand-scoped grouping one level above Categories.

Creates reporting_groups (with its own RPG-000001 ref sequence, same mechanism
as migration 0013) and seeds one system default reporting group per existing
brand. Adds categories.reporting_group_id as a NOT NULL FK, backfilled to each
brand's default group before the constraint is applied.

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reporting_groups, seed brand defaults, and require it on every category."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS reporting_groups_ref_seq START 1 INCREMENT 1")

    op.create_table(
        "reporting_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "ref",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text("'RPG-' || LPAD(nextval('reporting_groups_ref_seq')::text, 6, '0')"),
            comment="Human-readable reference ID, e.g. RPG-000001",
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reporting_groups_brand_id", "reporting_groups", ["brand_id"])
    # Only one default reporting group per brand
    op.create_index(
        "uq_reporting_groups_brand_default",
        "reporting_groups",
        ["brand_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # Seed the system default reporting group for every existing brand
    op.execute(
        "INSERT INTO reporting_groups (id, brand_id, name, is_default, is_system) "
        "SELECT gen_random_uuid(), id, 'Default', true, true FROM brands"
    )

    # Advance the sequence past the number of rows just inserted
    op.execute(
        "SELECT setval('reporting_groups_ref_seq', (SELECT COUNT(*) FROM reporting_groups) + 1, false)"
    )

    # Add the FK to categories, nullable first so the backfill can run
    op.add_column(
        "categories",
        sa.Column(
            "reporting_group_id",
            UUID(as_uuid=True),
            sa.ForeignKey("reporting_groups.id", ondelete="RESTRICT"),
            nullable=True,
            comment="Required reporting group this category rolls up to",
        ),
    )
    op.execute(
        "UPDATE categories SET reporting_group_id = rg.id "
        "FROM reporting_groups rg "
        "WHERE rg.brand_id = categories.brand_id AND rg.is_default"
    )
    op.alter_column("categories", "reporting_group_id", nullable=False)
    op.create_index("ix_categories_reporting_group_id", "categories", ["reporting_group_id"])


def downgrade() -> None:
    """Drop the reporting_group_id FK and the reporting_groups table."""
    op.drop_index("ix_categories_reporting_group_id", table_name="categories")
    op.drop_column("categories", "reporting_group_id")
    op.drop_index("uq_reporting_groups_brand_default", table_name="reporting_groups")
    op.drop_index("ix_reporting_groups_brand_id", table_name="reporting_groups")
    op.drop_table("reporting_groups")
    op.execute("DROP SEQUENCE IF EXISTS reporting_groups_ref_seq")
