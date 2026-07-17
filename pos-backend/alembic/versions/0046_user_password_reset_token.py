"""Add password-reset token columns to users.

Password-reset-by-email exists today only for SuperAdmin portal accounts
(portal_auth_service.py + SuperAdmin.password_reset_token). POS Users had no
equivalent, so a management caller had no way to trigger a reset email for a
colleague who forgot their password. This mirrors SuperAdmin's columns
exactly so user_service can reuse the same request/reset/expiry mechanism.

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable password_reset_token (+ expiry) columns to users."""
    op.add_column(
        "users",
        sa.Column(
            "password_reset_token",
            sa.String(length=255),
            nullable=True,
            comment="Single-use token for the forgot-password flow; NULL when no reset is pending",
        ),
    )
    op.create_unique_constraint("uq_users_password_reset_token", "users", ["password_reset_token"])
    op.add_column(
        "users",
        sa.Column("password_reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the password-reset token columns."""
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_constraint("uq_users_password_reset_token", "users", type_="unique")
    op.drop_column("users", "password_reset_token")
