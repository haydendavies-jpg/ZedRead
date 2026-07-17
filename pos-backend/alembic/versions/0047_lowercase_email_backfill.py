"""Backfill users.email and superadmins.email to lowercase.

Login/identity lookups are now case-insensitive at the application layer
(app.utils.security.normalize_email + func.lower() comparisons), but existing
rows written before this change may still carry mixed-case email addresses.
Backfilling keeps stored data consistent with what every future write will
produce, and makes a plain case-sensitive query correct as a fallback.

users.email has no unique constraint (dropped in migration 0031 — the same
person may manage multiple entities as Master User), so a case-only
duplicate (e.g. "Jane@x.com" and "jane@x.com" both existing as separate
rows) is left as two distinct lowercase rows rather than merged — merging
identities is a data-migration decision beyond the scope of this fix.
superadmins.email is unique; if a case-only collision exists there the
UPDATE will violate the constraint and surface for manual resolution rather
than silently picking a winner.

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-17
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Lowercase every non-null email in users and superadmins."""
    op.execute("UPDATE users SET email = lower(email) WHERE email IS NOT NULL AND email != lower(email)")
    op.execute(
        "UPDATE superadmins SET email = lower(email) WHERE email IS NOT NULL AND email != lower(email)"
    )


def downgrade() -> None:
    """No-op — original casing is not recoverable once lowercased."""
    pass
