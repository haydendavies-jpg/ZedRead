"""Add created_by_id to groups, for Reseller Staff own-accounts-only scoping.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md §5.1).
Reseller Staff SuperAdmins may only see/manage Groups they personally
created; Admin SuperAdmins are unrestricted. This requires Group to track
which SuperAdmin created it.

This migration:
1. Adds the nullable `created_by_id` column to `groups`, a FK to
   `superadmins.id` (nullable since pre-existing Groups have no recorded
   creator and Admin-created Groups are intentionally unscoped either way).

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable created_by_id FK column to groups."""
    op.add_column(
        "groups",
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_groups_created_by_id_superadmins",
        "groups",
        "superadmins",
        ["created_by_id"],
        ["id"],
    )


def downgrade() -> None:
    """Drop the created_by_id FK column from groups."""
    op.drop_constraint("fk_groups_created_by_id_superadmins", "groups", type_="foreignkey")
    op.drop_column("groups", "created_by_id")
