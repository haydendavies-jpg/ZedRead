"""Drop unique constraint on users.email to allow shared emails across master users.

The same operator may manage multiple entities (a Group and its Brands/Sites) using
a single login email. The original unique constraint from migration 0005 blocks this.
We retain a non-unique index for query performance.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-02
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the column-level unique constraint and the explicit unique index on users.email."""
    # Column-level UNIQUE constraint created by migration 0005's unique=True on the column
    op.drop_constraint("pos_users_email_key", "users", type_="unique")
    # Explicit unique index created in 0005 as ix_pos_users_email, renamed to ix_users_email in 0021
    op.drop_index("ix_users_email", table_name="users")
    # Recreate as non-unique — keeps query performance, removes the uniqueness requirement
    op.create_index("ix_users_email", "users", ["email"], unique=False)


def downgrade() -> None:
    """Restore the unique index and constraint on users.email."""
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    # Column constraint name is deterministic from the original table creation
    op.create_unique_constraint("pos_users_email_key", "users", ["email"])
