"""Add access_profile_page_permissions table for the page-category permission hierarchy.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md §4).
A row grants a single portal page (app.constants.pages.PAGE_CATALOG) to an
AccessProfile; presence means granted. A category tab is shown if any page
within it is granted, combined at the service layer with the site's
license plan as an independent gate.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the access_profile_page_permissions table."""
    op.create_table(
        "access_profile_page_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "access_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("access_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("access_profile_id", "page_key", name="uq_profile_page"),
    )
    op.create_index(
        "ix_access_profile_page_permissions_access_profile_id",
        "access_profile_page_permissions",
        ["access_profile_id"],
    )


def downgrade() -> None:
    """Drop the access_profile_page_permissions table."""
    op.drop_index(
        "ix_access_profile_page_permissions_access_profile_id",
        table_name="access_profile_page_permissions",
    )
    op.drop_table("access_profile_page_permissions")
