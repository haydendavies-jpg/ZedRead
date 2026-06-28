"""Business logic for AccessProfile seeding and management.

System profiles (Admin, Reporting Only, Manager, Staff, Master User) are seeded
automatically when a brand is created via seed_system_profiles(). The function
is idempotent — calling it twice on the same brand will not create duplicates.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.statuses import SystemAccessProfile
from app.models.access_profile import AccessProfile

log = structlog.get_logger(__name__)


async def seed_system_profiles(
    db: AsyncSession,
    brand_id: uuid.UUID,
) -> list[AccessProfile]:
    """
    Create the five system access profiles for a brand if they do not exist.

    Idempotent: checks for existing system profiles by name before inserting,
    so re-running against the same brand is safe (no duplicates).

    Called inside create_brand() in the same transaction, so all profiles
    are committed or rolled back atomically with the brand itself.

    This seeds the Master User *profile* (the permission tier definition)
    same as the other four — but unlike the other four, no User is ever
    assigned this profile here. That only happens once per site, in
    site_service.create_site(), which enforces the one-per-site constraint.

    Args:
        db: Active database session (transaction already open from caller).
        brand_id: UUID of the brand to seed profiles for.

    Returns:
        list[AccessProfile]: The newly created profiles (empty list if all existed).
    """
    # Load names of any system profiles that already exist for this brand
    result = await db.execute(
        select(AccessProfile.name).where(
            AccessProfile.brand_id == brand_id,
            AccessProfile.is_system == True,  # noqa: E712
        )
    )
    existing_names: set[str] = {row[0] for row in result}

    created: list[AccessProfile] = []
    for profile_name in SystemAccessProfile:
        if profile_name.value in existing_names:
            # Already seeded — skip to keep the operation idempotent
            log.debug(
                "access_profile.seed.skipped",
                brand_id=str(brand_id),
                name=profile_name.value,
            )
            continue

        # Admin, Reporting Only, and Master User get portal access by default;
        # Manager and Staff do not
        can_access_portal = profile_name in (
            SystemAccessProfile.ADMIN,
            SystemAccessProfile.REPORTING_ONLY,
            SystemAccessProfile.MASTER,
        )
        profile = AccessProfile(
            id=uuid.uuid4(),
            brand_id=brand_id,
            name=profile_name.value,
            is_system=True,
            is_active=True,
            can_access_portal=can_access_portal,
        )
        db.add(profile)
        created.append(profile)
        log.debug(
            "access_profile.seed.created",
            brand_id=str(brand_id),
            name=profile_name.value,
        )

    log.info(
        "access_profile.seed.complete",
        brand_id=str(brand_id),
        created_count=len(created),
    )
    return created
