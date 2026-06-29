"""Add first_name/last_name to users; relax email/password_hash to nullable.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md §2,
"Required fields"). Target rules:
- first_name/last_name are required for every User except Master User.
- email is only required once a User has a grant with a backend_role set.
- password_hash is only required alongside email.

These rules are enforced at the application layer (routes/services), not as
DB constraints, mirroring the existing is_master_user exception pattern —
this migration only relaxes/adds columns so the DB can represent the target
states (e.g. a Staff user with no email yet).

This migration:
1. Adds nullable `first_name`/`last_name` columns to `users`.
2. Backfills first_name/last_name for existing non-Master-User rows by
   splitting the existing `name` column on the first space (lossy for
   single-word names — best-effort only, matches the 0014/0022/0023 pattern
   of best-effort backfills for pre-existing data).
3. Drops the NOT NULL constraint on `email` and `password_hash` so a User
   can exist without backend-access credentials.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add first_name/last_name and relax email/password_hash to nullable."""
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))

    # Best-effort backfill: split "name" on the first space. Master Users are
    # excluded — their display name is the site's name, not a person's name.
    op.execute(
        "UPDATE users SET "
        "    first_name = split_part(name, ' ', 1), "
        "    last_name = NULLIF(substring(name FROM position(' ' IN name) + 1), '') "
        "WHERE is_master_user = false AND position(' ' IN name) > 0"
    )
    op.execute(
        "UPDATE users SET first_name = name "
        "WHERE is_master_user = false AND position(' ' IN name) = 0"
    )

    op.alter_column("users", "email", nullable=True)
    op.alter_column("users", "password_hash", nullable=True)


def downgrade() -> None:
    """Restore NOT NULL on email/password_hash and drop first_name/last_name."""
    op.alter_column("users", "password_hash", nullable=False)
    op.alter_column("users", "email", nullable=False)
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
