"""Collapse the 4 system access profiles into the 5 target User roles.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md). The
4 existing system access_profiles (Manager, Supervisor, Cashier, Kitchen)
are replaced by the brand-seedable subset of the 5 target roles (Admin,
Reporting Only, Manager, Staff) — Master User is excluded since it is
assigned per-site, not per-brand, and is out of scope for this migration.

Existing rows are renamed in place (their id is preserved, so any
user_access_grants FK referencing them keeps working unchanged):
    Manager    -> Admin     (can_access_portal stays True)
    Supervisor -> Manager   (can_access_portal becomes False)
    Cashier    -> Staff     (can_access_portal stays False)
    Kitchen    -> Staff     (can_access_portal stays False)

Cashier and Kitchen both collapse to "Staff", so a brand that had both will
end up with two distinct system rows both named "Staff" — this is a known,
accepted side effect (no data is lost, both keep their own grants) and can
be tidied up in a future follow-up if needed.

A "Reporting Only" system profile did not exist before, so this migration
inserts one for every existing brand that doesn't already have one,
matching what seed_system_profiles() now creates for new brands.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename legacy system profiles to the 4 brand-level target roles."""
    op.execute(
        "UPDATE access_profiles SET name = 'Admin', can_access_portal = true "
        "WHERE name = 'Manager' AND is_system = true"
    )
    op.execute(
        "UPDATE access_profiles SET name = 'Manager', can_access_portal = false "
        "WHERE name = 'Supervisor' AND is_system = true"
    )
    op.execute(
        "UPDATE access_profiles SET name = 'Staff', can_access_portal = false "
        "WHERE name IN ('Cashier', 'Kitchen') AND is_system = true"
    )
    # Backfill the new "Reporting Only" profile for brands that pre-date it
    op.execute(
        sa.text(
            "INSERT INTO access_profiles "
            "    (id, brand_id, name, is_system, is_active, can_access_portal) "
            "SELECT "
            "    gen_random_uuid(), b.id, 'Reporting Only', true, true, true "
            "FROM brands b "
            "WHERE NOT EXISTS ( "
            "    SELECT 1 FROM access_profiles ap "
            "    WHERE ap.brand_id = b.id "
            "      AND ap.name = 'Reporting Only' "
            "      AND ap.is_system = true "
            ")"
        )
    )


def downgrade() -> None:
    """Revert renamed profiles back to their legacy names.

    Reversal is best-effort: Cashier and Kitchen were merged into a single
    "Staff" name and cannot be distinguished again, so both renamed rows are
    restored to "Cashier" — this is an acceptable approximation for a
    downgrade path, not a lossless inverse.
    """
    op.execute(
        "DELETE FROM access_profiles WHERE name = 'Reporting Only' AND is_system = true "
        "  AND id NOT IN (SELECT DISTINCT access_profile_id FROM user_access_grants)"
    )
    op.execute(
        "UPDATE access_profiles SET name = 'Cashier', can_access_portal = false "
        "WHERE name = 'Staff' AND is_system = true"
    )
    op.execute(
        "UPDATE access_profiles SET name = 'Supervisor', can_access_portal = false "
        "WHERE name = 'Manager' AND is_system = true"
    )
    op.execute(
        "UPDATE access_profiles SET name = 'Manager', can_access_portal = true "
        "WHERE name = 'Admin' AND is_system = true"
    )
