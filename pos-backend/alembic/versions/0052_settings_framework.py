"""Android POS Phase 2 — settings framework (setting_values table).

The catalog of valid setting keys (label/category/type/options/default)
lives in code (app/constants/settings.py), not the database — this table
only stores brand- and site-level overrides. A brand-level default has
site_id NULL; a site-level override has site_id set. Two partial unique
indexes enforce at most one row per (brand, key) at brand level and per
(site, key) at site level, since a plain composite unique index can't
express "unique except when NULL" the way Postgres treats NULLs.

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create setting_values."""
    op.create_table(
        "setting_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("brands.id", ondelete="CASCADE"),
            nullable=False,
            comment="Brand this override belongs to — set even for a site-level row",
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL for a brand-level default; set for a site-level override",
        ),
        sa.Column(
            "setting_key",
            sa.String(100),
            nullable=False,
            comment="Key from the code-defined catalog in app/constants/settings.py",
        ),
        sa.Column(
            "value",
            postgresql.JSONB(),
            nullable=False,
            comment="JSON-wrapped value, e.g. {'value': true} — type validated against the catalog entry",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_setting_values_brand_id", "setting_values", ["brand_id"])
    op.create_index("ix_setting_values_site_id", "setting_values", ["site_id"])
    op.create_index(
        "uq_setting_values_brand_default",
        "setting_values",
        ["brand_id", "setting_key"],
        unique=True,
        postgresql_where=sa.text("site_id IS NULL"),
    )
    op.create_index(
        "uq_setting_values_site_override",
        "setting_values",
        ["site_id", "setting_key"],
        unique=True,
        postgresql_where=sa.text("site_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop setting_values."""
    op.drop_index("uq_setting_values_site_override", table_name="setting_values")
    op.drop_index("uq_setting_values_brand_default", table_name="setting_values")
    op.drop_index("ix_setting_values_site_id", table_name="setting_values")
    op.drop_index("ix_setting_values_brand_id", table_name="setting_values")
    op.drop_table("setting_values")
