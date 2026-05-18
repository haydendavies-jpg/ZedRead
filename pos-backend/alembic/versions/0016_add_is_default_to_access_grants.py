"""Add is_default flag to user_access_grants.

Marks one grant per user as the primary/default entry point so login can
route directly to that grant when a user has multiple portal-capable grants.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add is_default column and set the earliest active site-scope grant as default per user."""
    op.add_column(
        "user_access_grants",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # For each user, promote their earliest active site-scope grant to is_default=True
    op.execute(sa.text(
        """
        UPDATE user_access_grants
        SET is_default = true
        WHERE id IN (
            SELECT DISTINCT ON (user_id) id
            FROM user_access_grants
            WHERE scope = 'site' AND is_active = true
            ORDER BY user_id, created_at ASC
        )
        """
    ))


def downgrade() -> None:
    """Remove is_default from user_access_grants."""
    op.drop_column("user_access_grants", "is_default")
