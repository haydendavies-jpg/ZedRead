"""Add password reset token columns to portal_users.

Supports the forgot-password / reset-password flow: a single-use token is
generated on request and stored alongside its expiry; both are cleared once
the password has been reset (or the token has expired).
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add password_reset_token and password_reset_token_expires_at to portal_users."""
    op.add_column(
        "portal_users",
        sa.Column(
            "password_reset_token",
            sa.String(255),
            nullable=True,
            comment="Single-use token for the forgot-password flow. NULL when no reset is pending.",
        ),
    )
    op.add_column(
        "portal_users",
        sa.Column(
            "password_reset_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Expiry for password_reset_token. NULL when no reset is pending.",
        ),
    )
    op.create_index(
        "ix_portal_users_password_reset_token",
        "portal_users",
        ["password_reset_token"],
        unique=True,
    )


def downgrade() -> None:
    """Remove password reset columns from portal_users."""
    op.drop_index("ix_portal_users_password_reset_token", table_name="portal_users")
    op.drop_column("portal_users", "password_reset_token_expires_at")
    op.drop_column("portal_users", "password_reset_token")
