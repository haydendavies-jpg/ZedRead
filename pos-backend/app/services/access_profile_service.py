"""Business logic for AccessProfile seeding and management.

System profiles (Admin, Reporting Only, Manager, Staff, Master User) are seeded
automatically when a brand is created via seed_system_profiles(). The function
is idempotent — calling it twice on the same brand will not create duplicates.

Also holds the page-category permission hierarchy (ROLE_MODEL.md §4): granting,
revoking, and resolving which pages an AccessProfile may see, combined with the
site's license plan as an independent gate.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_PROFILE_PAGE_GRANTED,
    ACCESS_PROFILE_PAGE_REVOKED,
)
from app.constants.license_plans import allowed_pages_for_plan
from app.constants.pages import PAGE_KEYS, pages_in_category
from app.constants.statuses import ActorType, PageCategory, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.license import License
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)

# Default page grants per system role (ROLE_MODEL.md §2). Master User and Admin
# get the full catalog; Reporting Only is limited to the Reports category;
# Manager defaults to broad-but-restrictable access (everything except the
# user-management and license-billing pages, which stay Admin-only by default);
# Staff defaults to a minimal, expandable set.
_DEFAULT_ROLE_PAGES: dict[SystemAccessProfile, frozenset[str]] = {
    SystemAccessProfile.MASTER: PAGE_KEYS,
    SystemAccessProfile.ADMIN: PAGE_KEYS,
    SystemAccessProfile.REPORTING_ONLY: frozenset(pages_in_category(PageCategory.REPORTS)),
    SystemAccessProfile.MANAGER: PAGE_KEYS - frozenset(
        {"users", "access_grants", "access_profiles", "license_billing"}
    ),
    SystemAccessProfile.STAFF: frozenset({"products", "categories", "customers"}),
}


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

        # Seed this role's default page grants (ROLE_MODEL.md §2/§4)
        for page_key in _DEFAULT_ROLE_PAGES[profile_name]:
            db.add(
                AccessProfilePagePermission(
                    id=uuid.uuid4(),
                    access_profile_id=profile.id,
                    page_key=page_key,
                )
            )

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


async def seed_group_master_profile(
    db: AsyncSession,
    group_id: uuid.UUID,
) -> AccessProfile | None:
    """
    Create the single group-scoped Master User access profile for a group, if missing.

    Mirrors seed_system_profiles() but only seeds the one Master User tier,
    scoped to the group rather than a brand (AccessProfile.group_id set,
    brand_id NULL) — the other four system tiers (Admin, Reporting Only,
    Manager, Staff) stay brand-only since they gate catalog/product
    permissions that only make sense once a Brand exists.

    Idempotent: returns None without inserting if a group-scoped Master
    profile already exists for this group.

    Called inside create_group() in the same transaction, so the profile is
    committed or rolled back atomically with the group itself.

    Args:
        db: Active database session (transaction already open from caller).
        group_id: UUID of the group to seed the Master profile for.

    Returns:
        AccessProfile | None: The newly created profile, or None if it already existed.
    """
    result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.group_id == group_id,
            AccessProfile.name == SystemAccessProfile.MASTER.value,
            AccessProfile.is_system == True,  # noqa: E712
        )
    )
    if result.scalar_one_or_none() is not None:
        log.debug("access_profile.seed_group_master.skipped", group_id=str(group_id))
        return None

    profile = AccessProfile(
        id=uuid.uuid4(),
        group_id=group_id,
        name=SystemAccessProfile.MASTER.value,
        is_system=True,
        is_active=True,
        can_access_portal=True,
    )
    db.add(profile)

    # Master User gets the full page catalog, same as the brand-level tier
    for page_key in PAGE_KEYS:
        db.add(
            AccessProfilePagePermission(
                id=uuid.uuid4(),
                access_profile_id=profile.id,
                page_key=page_key,
            )
        )

    log.info("access_profile.seed_group_master.created", group_id=str(group_id))
    return profile


async def _load_profile_or_404(db: AsyncSession, access_profile_id: uuid.UUID) -> AccessProfile:
    """
    Load an AccessProfile by id, raising 404 if it does not exist.

    Args:
        db: Active database session.
        access_profile_id: UUID of the profile to load.

    Returns:
        AccessProfile: The loaded profile.

    Raises:
        HTTPException: 404 if no profile exists with this id.
    """
    result = await db.execute(select(AccessProfile).where(AccessProfile.id == access_profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access profile not found")
    return profile


async def list_page_permissions(db: AsyncSession, access_profile_id: uuid.UUID) -> list[str]:
    """
    List the page keys currently granted to an AccessProfile.

    Args:
        db: Active database session.
        access_profile_id: UUID of the profile to query.

    Returns:
        list[str]: Granted page keys, sorted for stable output.

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    await _load_profile_or_404(db, access_profile_id)
    result = await db.execute(
        select(AccessProfilePagePermission.page_key).where(
            AccessProfilePagePermission.access_profile_id == access_profile_id
        )
    )
    return sorted(row[0] for row in result)


async def grant_page(
    db: AsyncSession,
    access_profile_id: uuid.UUID,
    page_key: str,
    actor: User | SuperAdmin,
) -> None:
    """
    Grant a single page to an AccessProfile, idempotently.

    Args:
        db: Active database session.
        access_profile_id: UUID of the profile to grant the page to.
        page_key: Key from app.constants.pages.PAGE_CATALOG to grant.
        actor: The User or SuperAdmin performing the grant, for audit attribution.

    Raises:
        HTTPException: 404 if the profile does not exist.
        HTTPException: 422 if page_key is not a recognised page.
    """
    await _load_profile_or_404(db, access_profile_id)
    if page_key not in PAGE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown page_key: {page_key}",
        )

    existing = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == access_profile_id,
            AccessProfilePagePermission.page_key == page_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        # Already granted — nothing to do, keeps the operation idempotent
        return

    db.add(
        AccessProfilePagePermission(
            id=uuid.uuid4(),
            access_profile_id=access_profile_id,
            page_key=page_key,
        )
    )

    await log_action(
        db=db,
        action=ACCESS_PROFILE_PAGE_GRANTED,
        entity_type="access_profile_page_permission",
        entity_id=f"{access_profile_id}:{page_key}",
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=getattr(actor, "name", None),
        after_state={"access_profile_id": str(access_profile_id), "page_key": page_key},
    )
    await db.commit()

    log.info("access_profile.page.granted", access_profile_id=str(access_profile_id), page_key=page_key)


async def revoke_page(
    db: AsyncSession,
    access_profile_id: uuid.UUID,
    page_key: str,
    actor: User | SuperAdmin,
) -> None:
    """
    Revoke a single page from an AccessProfile.

    Args:
        db: Active database session.
        access_profile_id: UUID of the profile to revoke the page from.
        page_key: Key from app.constants.pages.PAGE_CATALOG to revoke.
        actor: The User or SuperAdmin performing the revoke, for audit attribution.

    Raises:
        HTTPException: 404 if the profile does not exist, or the page is not granted.
    """
    await _load_profile_or_404(db, access_profile_id)

    existing = await db.execute(
        select(AccessProfilePagePermission).where(
            AccessProfilePagePermission.access_profile_id == access_profile_id,
            AccessProfilePagePermission.page_key == page_key,
        )
    )
    permission = existing.scalar_one_or_none()
    if permission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page is not granted to this profile")

    await db.delete(permission)

    await log_action(
        db=db,
        action=ACCESS_PROFILE_PAGE_REVOKED,
        entity_type="access_profile_page_permission",
        entity_id=f"{access_profile_id}:{page_key}",
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=getattr(actor, "name", None),
        before_state={"access_profile_id": str(access_profile_id), "page_key": page_key},
    )
    await db.commit()

    log.info("access_profile.page.revoked", access_profile_id=str(access_profile_id), page_key=page_key)


async def resolve_visible_pages(db: AsyncSession, access_profile_id: uuid.UUID, site_id: uuid.UUID) -> frozenset[str]:
    """
    Resolve the pages visible to a holder of an AccessProfile at a given site.

    Combines the two independent gates described in ROLE_MODEL.md §4:
    ``visible = has_role_permission AND license_allows``. The role grant comes
    from AccessProfilePagePermission rows; the license gate comes from the
    site's License.plan_name via app.constants.license_plans.

    Args:
        db: Active database session.
        access_profile_id: UUID of the profile to resolve pages for.
        site_id: UUID of the site whose license plan supplies the license gate.

    Returns:
        frozenset[str]: Page keys visible under both gates.

    Raises:
        HTTPException: 404 if the profile does not exist.
    """
    granted = frozenset(await list_page_permissions(db, access_profile_id))

    license_r = await db.execute(select(License).where(License.site_id == site_id))
    license_row = license_r.scalar_one_or_none()
    plan_name = license_row.plan_name if license_row else None

    return granted & allowed_pages_for_plan(plan_name)
