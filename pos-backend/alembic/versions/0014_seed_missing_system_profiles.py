"""Seed system access profiles for brands that were created before seeding was wired up.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# System profiles to ensure exist for every brand (name, can_access_portal).
# One INSERT … SELECT per profile — idempotent via NOT EXISTS guard.
_SYSTEM_PROFILES = [
    ("Manager",    True),
    ("Supervisor", False),
    ("Cashier",    False),
    ("Kitchen",    False),
]


def upgrade() -> None:
    """Insert missing system access profiles for all existing brands."""
    for profile_name, can_access_portal in _SYSTEM_PROFILES:
        op.execute(
            sa.text(
                "INSERT INTO access_profiles "
                "    (id, brand_id, name, is_system, is_active, can_access_portal) "
                "SELECT "
                "    gen_random_uuid(), b.id, :name, true, true, :cap "
                "FROM brands b "
                "WHERE NOT EXISTS ( "
                "    SELECT 1 FROM access_profiles ap "
                "    WHERE ap.brand_id = b.id "
                "      AND ap.name = :name "
                "      AND ap.is_system = true "
                ")"
            ).bindparams(name=profile_name, cap=can_access_portal)
        )


def downgrade() -> None:
    """Remove system profiles inserted by this migration (only if unreferenced)."""
    for profile_name, _ in _SYSTEM_PROFILES:
        op.execute(
            sa.text(
                "DELETE FROM access_profiles "
                "WHERE name = :name AND is_system = true "
                "  AND id NOT IN ("
                "      SELECT DISTINCT access_profile_id FROM user_access_grants"
                "  )"
            ).bindparams(name=profile_name)
        )
