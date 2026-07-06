"""Add token_version to superadmins and users for JWT revocation.

Each portal/management token embeds the identity's token_version as a 'tv'
claim. Bumping the column (password change/reset, logout-everywhere) makes all
previously issued tokens for that identity fail validation.

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add token_version INTEGER NOT NULL DEFAULT 0 to superadmins and users."""
    op.add_column(
        "superadmins",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Remove token_version from superadmins and users."""
    op.drop_column("users", "token_version")
    op.drop_column("superadmins", "token_version")
