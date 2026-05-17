"""Seed system access profiles for brands that were created before seeding was wired up.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# System profiles to ensure exist for every brand.
# Manager gets portal access; the rest do not.
_SYSTEM_PROFILES = [
    ("Manager",    True),
    ("Supervisor", False),
    ("Cashier",    False),
    ("Kitchen",    False),
]


def upgrade() -> None:
    """Insert missing system access profiles for all existing brands."""
    conn = op.get_bind()

    # Fetch all brand IDs
    brands = conn.execute(sa.text("SELECT id FROM brands")).fetchall()

    for (brand_id,) in brands:
        for profile_name, can_access_portal in _SYSTEM_PROFILES:
            # Check if this system profile already exists for this brand
            existing = conn.execute(
                sa.text(
                    "SELECT id FROM access_profiles "
                    "WHERE brand_id = :brand_id AND name = :name AND is_system = true"
                ),
                {"brand_id": brand_id, "name": profile_name},
            ).fetchone()

            if existing:
                continue  # idempotent — already seeded

            conn.execute(
                sa.text(
                    "INSERT INTO access_profiles "
                    "(id, brand_id, name, is_system, is_active, can_access_portal) "
                    "VALUES (:id, :brand_id, :name, true, true, :cap)"
                ),
                {
                    "id": uuid.uuid4(),
                    "brand_id": brand_id,
                    "name": profile_name,
                    "cap": can_access_portal,
                },
            )


def downgrade() -> None:
    """Remove system profiles that were inserted by this migration.

    Only removes profiles that have no grants referencing them, to avoid
    breaking existing data.
    """
    conn = op.get_bind()
    for profile_name, _ in _SYSTEM_PROFILES:
        conn.execute(
            sa.text(
                "DELETE FROM access_profiles "
                "WHERE name = :name AND is_system = true "
                "AND id NOT IN (SELECT DISTINCT access_profile_id FROM user_access_grants)"
            ),
            {"name": profile_name},
        )
