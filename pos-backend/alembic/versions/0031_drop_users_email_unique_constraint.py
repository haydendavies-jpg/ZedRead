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
    """Drop every unique constraint/index on users.email, then recreate a non-unique index.

    Object names vary by how the database was originally provisioned: a pure
    migration history yields pos_users_email_key (constraint from 0005's
    unique=True, name survives 0021's table rename) and ix_users_email
    (0005's ix_pos_users_email, renamed in 0021), but a database bootstrapped
    from metadata would name the constraint users_email_key instead. Use
    IF EXISTS on all known variants so this migration succeeds against any of
    those states instead of crashing app startup.
    """
    # Column-level UNIQUE constraint — both possible names depending on provenance
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS pos_users_email_key")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")
    # Explicit unique index — current name and pre-0021 name
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute("DROP INDEX IF EXISTS ix_pos_users_email")
    # Recreate as non-unique — keeps query performance, removes the uniqueness requirement
    op.create_index("ix_users_email", "users", ["email"], unique=False)


def downgrade() -> None:
    """Restore the unique index and constraint on users.email."""
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    # Column constraint name is deterministic from the original table creation
    op.create_unique_constraint("pos_users_email_key", "users", ["email"])
