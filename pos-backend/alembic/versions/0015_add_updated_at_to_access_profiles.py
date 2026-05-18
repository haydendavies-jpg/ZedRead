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
    """Add updated_at to access_profiles if missing, back-filling existing rows.

    Uses IF NOT EXISTS so the migration is safe on fresh databases where
    migration 0005 already created the column, and on production databases
    where 0005 predates the column addition.
    """
    op.execute(sa.text(
        "ALTER TABLE access_profiles ADD COLUMN IF NOT EXISTS updated_at"
        " TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
    ))
    # Back-fill any rows where updated_at > created_at (i.e. just got the NOW() default)
    op.execute(sa.text(
        "UPDATE access_profiles SET updated_at = created_at WHERE updated_at > created_at"
    ))


def downgrade() -> None:
    """Remove updated_at from access_profiles."""
    op.drop_column("access_profiles", "updated_at")
