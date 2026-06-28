"""Add the Master User role: one immutable site-identity User per site.

Part of Stage 15 (Identity & Permissions Redesign, see ROLE_MODEL.md). Adds
the 5th target role, Master User — exactly one per site, full fixed POS
access, always-on backend access, display name = the site's name. Unlike
the other 4 system access_profiles, Master User is never freely assigned;
it is auto-created alongside its site going forward (site_service.create_site()).

This migration:
1. Adds the `is_master_user` column to `users`.
2. Backfills a "Master User" system access_profile for every existing brand
   (mirrors the 0022 pattern used for "Reporting Only").
3. Backfills a Master User + site-scope grant for every existing site that
   doesn't already have one. Credentials are synthetic/unusable — Master
   User has no real login path yet (deferred to the required-field-rules
   slice in ROLE_MODEL.md).

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

# Precomputed argon2 hash of a random, never-recorded value — Master Users
# have no real login path yet, this just satisfies the NOT NULL constraint.
_SENTINEL_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$ZhKRbTRU6by9sP5bdsiCBg$"
    "b06XzrNxOPh+qe+EC8j/na9Kv8uGehuw7B/DJQ46lv4"
)


def upgrade() -> None:
    """Add is_master_user and backfill the role for every existing site."""
    op.add_column(
        "users",
        sa.Column(
            "is_master_user",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    op.execute(
        "INSERT INTO access_profiles "
        "    (id, brand_id, name, is_system, is_active, can_access_portal) "
        "SELECT "
        "    gen_random_uuid(), b.id, 'Master User', true, true, true "
        "FROM brands b "
        "WHERE NOT EXISTS ( "
        "    SELECT 1 FROM access_profiles ap "
        "    WHERE ap.brand_id = b.id "
        "      AND ap.name = 'Master User' "
        "      AND ap.is_system = true "
        ")"
    )

    op.execute(
        sa.text(
            "WITH missing_sites AS ( "
            "    SELECT s.id AS site_id, s.brand_id AS brand_id, s.name AS site_name "
            "    FROM sites s "
            "    WHERE NOT EXISTS ( "
            "        SELECT 1 FROM user_access_grants g "
            "        JOIN users u ON u.id = g.user_id "
            "        WHERE g.site_id = s.id AND u.is_master_user = true "
            "    ) "
            "), "
            "inserted_users AS ( "
            "    INSERT INTO users (id, brand_id, name, email, password_hash, is_active, is_master_user) "
            "    SELECT "
            "        gen_random_uuid(), ms.brand_id, ms.site_name, "
            "        'master-' || ms.site_id || '@system.zedread.internal', "
            "        :hash, true, true "
            "    FROM missing_sites ms "
            "    RETURNING id, email "
            ") "
            "INSERT INTO user_access_grants "
            "    (id, user_id, scope, site_id, access_profile_id, is_active, is_default, backend_role) "
            "SELECT "
            "    gen_random_uuid(), iu.id, 'site', ms.site_id, ap.id, true, true, 'admin' "
            "FROM inserted_users iu "
            "JOIN missing_sites ms "
            "    ON 'master-' || ms.site_id || '@system.zedread.internal' = iu.email "
            "JOIN access_profiles ap "
            "    ON ap.brand_id = ms.brand_id AND ap.name = 'Master User' AND ap.is_system = true"
        ).bindparams(hash=_SENTINEL_PASSWORD_HASH)
    )


def downgrade() -> None:
    """Remove Master Users, their grants, and the Master User profile/column."""
    op.execute(
        "DELETE FROM user_access_grants "
        "WHERE user_id IN (SELECT id FROM users WHERE is_master_user = true)"
    )
    op.execute("DELETE FROM users WHERE is_master_user = true")
    op.execute(
        "DELETE FROM access_profiles WHERE name = 'Master User' AND is_system = true "
        "  AND id NOT IN (SELECT DISTINCT access_profile_id FROM user_access_grants)"
    )
    op.drop_column("users", "is_master_user")
