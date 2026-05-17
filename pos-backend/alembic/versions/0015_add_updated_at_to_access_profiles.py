"""Add missing updated_at column to access_profiles table.

The ORM model declares updated_at but migration 0005 did not include it,
causing every SELECT and INSERT on access_profiles to fail with
UndefinedColumnError. This is the root cause of the empty access-profile
dropdown and the 500 on POST /brands/.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add updated_at to access_profiles, back-filling existing rows with created_at."""
    op.add_column(
        "access_profiles",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Back-fill existing rows so updated_at matches created_at
    op.execute(sa.text("UPDATE access_profiles SET updated_at = created_at"))


def downgrade() -> None:
    """Remove updated_at from access_profiles."""
    op.drop_column("access_profiles", "updated_at")
