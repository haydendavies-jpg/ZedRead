"""Business logic for POS user access grant management.

Scope enforcement rules:
  group-scope management user  → can create brand-scope or site-scope grants
                                  within their group
  brand-scope management user  → can create site-scope grants within their brand
  site-scope management user   → cannot create grants (read-only)
  portal admin                 → full authority (bypasses scope checks)

Role ceiling rule (Stage 17): a management user can only create or update a
grant to an access profile ranked at or below the rank of the profile they
themselves hold (see _ROLE_RANK below) — they can never delegate a level of
access higher than their own. Portal admins bypass this, same as the scope
check. The Master User profile can never be granted through this service at
all (for any caller, including portal admins) — it is auto-created exactly
once per site by site_service.create_site() and is never delegated into.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_BACKEND_ROLE_UPDATED,
    ACCESS_GRANT_CREATED,
    ACCESS_GRANT_DEFAULT_SET,
    ACCESS_GRANT_REVOKED,
    ACCESS_PROFILE_PORTAL_UPDATED,
)
from app.constants.statuses import ActorType, GrantScope, SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.schemas.access_grant import AccessGrantBulkUpdate, AccessGrantCreate, AccessGrantUpdate
from app.services.audit_service import log_action
from app.utils.dependencies import ManagementAccess

log = structlog.get_logger(__name__)

# Valid backend_role values a grant may carry — mirrors routes/users.py so the
# grant update path validates the same set. Defined here (rather than only in
# the route) because update_grant() references it; without it, updating a grant's
# backend_role raised NameError at runtime.
_BACKEND_ROLES = {"admin", "users", "reporting"}


async def _load_grant_with_authority(
    db: AsyncSession,
    grant_id: uuid.UUID,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> UserAccessGrant:
    """
    Load a grant and verify the caller has authority over it.

    Portal users have full authority. Management users must have the grant
    within their scope (site/brand/group boundary check).

    Args:
        db: Active session.
        grant_id: The grant to load.
        management_access: Set if caller is a management JWT user.
        superadmin: Set if caller is a portal admin.

    Returns:
        UserAccessGrant: The verified grant.

    Raises:
        HTTPException: 404 if not found, 403 if outside caller's scope.
    """
    result = await db.execute(
        select(UserAccessGrant).where(UserAccessGrant.id == grant_id)
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")

    if superadmin:
        return grant  # Portal admin has full authority

    # Management user — verify the grant is within their scope
    assert management_access is not None  # one of the two must be set
    await _assert_grant_in_scope(db, grant, management_access)
    return grant


async def _assert_grant_in_scope(
    db: AsyncSession,
    grant: UserAccessGrant,
    access: ManagementAccess,
) -> None:
    """
    Raise HTTP 403 if the grant is outside the management user's scope.

    Args:
        db: Active session.
        grant: The grant to check.
        access: The management user's access context.

    Raises:
        HTTPException: 403 if the grant is not within the caller's scope.
    """
    scope = access.scope

    if scope == GrantScope.SITE:
        # Site-scope users can only see their own site's grants
        if grant.site_id != access.site.id:  # type: ignore[union-attr]
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your scope")

    elif scope == GrantScope.BRAND:
        # Brand-scope users can see all grants within their brand
        brand_id = access.brand.id  # type: ignore[union-attr]
        if grant.scope == GrantScope.SITE and grant.site_id:
            site_r = await db.execute(select(Site).where(Site.id == grant.site_id))
            site = site_r.scalar_one_or_none()
            if not site or site.brand_id != brand_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your brand scope")
        elif grant.scope == GrantScope.BRAND:
            if grant.brand_id != brand_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your brand scope")
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your brand scope")

    elif scope == GrantScope.GROUP:
        # Group-scope users can see all grants within their group
        group_id = access.group.id  # type: ignore[union-attr]
        if grant.scope == GrantScope.GROUP:
            if grant.group_id != group_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your group scope")
        elif grant.scope == GrantScope.BRAND and grant.brand_id:
            brand_r = await db.execute(select(Brand).where(Brand.id == grant.brand_id))
            brand = brand_r.scalar_one_or_none()
            if not brand or brand.group_id != group_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your group scope")
        elif grant.scope == GrantScope.SITE and grant.site_id:
            site_r = await db.execute(select(Site).where(Site.id == grant.site_id))
            site = site_r.scalar_one_or_none()
            if not site:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your group scope")
            brand_r = await db.execute(select(Brand).where(Brand.id == site.brand_id))
            brand = brand_r.scalar_one_or_none()
            if not brand or brand.group_id != group_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant is outside your group scope")


async def list_grants(
    db: AsyncSession,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
    brand_id_param: uuid.UUID | None,
    skip: int,
    limit: int,
) -> list[UserAccessGrant]:
    """
    List active access grants within the caller's authority.

    Portal users must supply brand_id_param to scope the results.
    Group-scope management users see all grants in their group.
    Brand-scope users see all grants in their brand.
    Site-scope users see only grants for their site.

    Args:
        db: Active session.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.
        brand_id_param: Optional brand_id filter (required for portal/group-scope).
        skip: Pagination offset.
        limit: Maximum results.

    Returns:
        list[UserAccessGrant]: Matching grants.
    """
    query = select(UserAccessGrant).where(UserAccessGrant.is_active == True)  # noqa: E712

    if superadmin:
        if brand_id_param:
            # Portal admin filtered to a brand
            sites_sq = select(Site.id).where(Site.brand_id == brand_id_param)
            query = query.where(
                (UserAccessGrant.brand_id == brand_id_param) |
                UserAccessGrant.site_id.in_(sites_sq)
            )
        # else: no filter — return all (expensive, but valid for portal admin)

    elif management_access:
        scope = management_access.scope
        if scope == GrantScope.SITE:
            query = query.where(UserAccessGrant.site_id == management_access.site.id)  # type: ignore[union-attr]
        elif scope == GrantScope.BRAND:
            brand_id = management_access.brand.id  # type: ignore[union-attr]
            sites_sq = select(Site.id).where(Site.brand_id == brand_id)
            query = query.where(
                (UserAccessGrant.brand_id == brand_id) |
                UserAccessGrant.site_id.in_(sites_sq)
            )
        elif scope == GrantScope.GROUP:
            group_id = management_access.group.id  # type: ignore[union-attr]
            brands_sq = select(Brand.id).where(Brand.group_id == group_id)
            sites_sq = select(Site.id).where(Site.brand_id.in_(brands_sq))
            query = query.where(
                (UserAccessGrant.group_id == group_id) |
                UserAccessGrant.brand_id.in_(brands_sq) |
                UserAccessGrant.site_id.in_(sites_sq)
            )

    result = await db.execute(query.offset(skip).limit(limit))
    return list(result.scalars().all())


async def search_grantable_users(
    db: AsyncSession,
    brand_id: uuid.UUID,
    query: str,
    limit: int,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> list[User]:
    """
    Search users by name or email within a brand, for the Grant Access user picker.

    Lets the portal search by a human-readable name/email instead of requiring
    the admin to paste a raw user UUID. Scope-checked the same way as
    list_access_profiles (routes/access_grants.py): site/brand-scope callers may
    only search their own brand; group-scope callers may search any brand in
    their group; portal admins may search any brand.

    Args:
        db: Active database session.
        brand_id: Brand to search within.
        query: Case-insensitive substring matched against name and email.
        limit: Maximum results to return.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.

    Returns:
        list[User]: Matching users, ordered by name.

    Raises:
        HTTPException: 403 if brand_id is outside a management caller's scope.
    """
    if management_access is not None:
        if management_access.scope in (GrantScope.SITE, GrantScope.BRAND):
            if management_access.brand is None or management_access.brand.id != brand_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand is outside your scope")
        elif management_access.scope == GrantScope.GROUP:
            brand_r = await db.execute(select(Brand).where(Brand.id == brand_id))
            brand = brand_r.scalar_one_or_none()
            if brand is None or management_access.group is None or brand.group_id != management_access.group.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand is outside your scope")

    q = select(User).where(User.brand_id == brand_id)
    if query:
        like = f"%{query}%"
        q = q.where(or_(User.name.ilike(like), User.email.ilike(like)))
    q = q.order_by(User.name).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_grant(
    db: AsyncSession,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
    payload: AccessGrantCreate,
) -> UserAccessGrant:
    """
    Create a new access grant, enforcing scope authority rules.

    Args:
        db: Active session.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.
        payload: Grant creation data.

    Returns:
        UserAccessGrant: The created grant.

    Raises:
        HTTPException: 403 if the caller lacks authority for the requested scope.
        HTTPException: 404 if the target user or profile does not exist.
        HTTPException: 409 if an active grant already exists for the same user/scope/entity.
    """
    # Verify the target user exists and belongs to a brand in scope
    user_r = await db.execute(select(User).where(User.id == payload.user_id))
    target_user = user_r.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target POS user not found")

    # Verify the access profile exists and is active
    profile_r = await db.execute(
        select(AccessProfile).where(
            AccessProfile.id == payload.access_profile_id,
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    access_profile = profile_r.scalar_one_or_none()
    if not access_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access profile not found or inactive")

    # Master User is auto-created once per site (site_service.create_site()) and
    # is never delegated into, by any caller (ROLE_MODEL.md §2, Stage 17).
    _assert_not_master_profile(access_profile)

    # Enforce scope authority if the caller is a management user (not portal admin)
    if management_access:
        await _assert_create_authority(db, management_access, payload)
        _assert_role_ceiling(management_access, access_profile)

    # Check for duplicate active grant
    dup_filter = [
        UserAccessGrant.user_id == payload.user_id,
        UserAccessGrant.scope == payload.scope,
        UserAccessGrant.is_active == True,  # noqa: E712
    ]
    if payload.scope == "site":
        dup_filter.append(UserAccessGrant.site_id == payload.site_id)
    elif payload.scope == "brand":
        dup_filter.append(UserAccessGrant.brand_id == payload.brand_id)
    elif payload.scope == "group":
        dup_filter.append(UserAccessGrant.group_id == payload.group_id)

    dup_r = await db.execute(select(UserAccessGrant).where(*dup_filter))
    if dup_r.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active grant already exists for this user at this scope/entity",
        )

    # Enforce single-group constraint: a user may only be in one group.
    # If creating a group-scope grant, verify no other group-scope grant exists
    # for a different group.
    if payload.scope == GrantScope.SITE and payload.site_id:
        site_r = await db.execute(select(Site).where(Site.id == payload.site_id))
        _site = site_r.scalar_one_or_none()
        if _site:
            brand_r = await db.execute(select(Brand).where(Brand.id == _site.brand_id))
            _brand = brand_r.scalar_one_or_none()
            if _brand:
                existing_group_r = await db.execute(
                    select(UserAccessGrant).where(
                        UserAccessGrant.user_id == payload.user_id,
                        UserAccessGrant.scope == GrantScope.GROUP,
                        UserAccessGrant.is_active == True,  # noqa: E712
                        UserAccessGrant.group_id != _brand.group_id,
                    )
                )
                if existing_group_r.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="User already belongs to a different group. A POS user can only belong to one group.",
                    )

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    granted_by = actor.id if isinstance(actor, User) else None

    # Auto-set is_default=True when this is the user's first active site-scope grant.
    # Subsequent site grants are non-default; admins can change the default via set_default_grant.
    is_default = False
    if payload.scope == GrantScope.SITE:
        existing_site_r = await db.execute(
            select(UserAccessGrant).where(
                UserAccessGrant.user_id == payload.user_id,
                UserAccessGrant.scope == GrantScope.SITE,
                UserAccessGrant.is_active.is_(True),
                UserAccessGrant.is_default.is_(True),
            ).limit(1)
        )
        if existing_site_r.scalar_one_or_none() is None:
            is_default = True

    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=payload.user_id,
        scope=payload.scope,
        site_id=payload.site_id,
        brand_id=payload.brand_id,
        group_id=payload.group_id,
        access_profile_id=payload.access_profile_id,
        granted_by_id=granted_by,
        is_active=True,
        is_default=is_default,
    )
    db.add(grant)

    await log_action(
        db=db,
        action=ACCESS_GRANT_CREATED,
        entity_type="user_access_grant",
        entity_id=str(grant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "user_id": str(payload.user_id),
            "scope": payload.scope,
            "access_profile_id": str(payload.access_profile_id),
        },
    )

    # Auto-create brand and group grants when assigning to a site.
    # This ensures the user is visible at all hierarchy levels and can
    # access the portal at brand/group scope if the profile allows it.
    if payload.scope == GrantScope.SITE and payload.site_id:
        site_r2 = await db.execute(select(Site).where(Site.id == payload.site_id))
        site = site_r2.scalar_one_or_none()
        if site:
            # Brand-scope grant — upsert only if no active brand grant exists for this brand
            brand_dup_r = await db.execute(
                select(UserAccessGrant).where(
                    UserAccessGrant.user_id == payload.user_id,
                    UserAccessGrant.scope == GrantScope.BRAND,
                    UserAccessGrant.brand_id == site.brand_id,
                    UserAccessGrant.is_active == True,  # noqa: E712
                )
            )
            if not brand_dup_r.scalar_one_or_none():
                brand_grant = UserAccessGrant(
                    id=uuid.uuid4(),
                    user_id=payload.user_id,
                    scope=GrantScope.BRAND,
                    brand_id=site.brand_id,
                    access_profile_id=payload.access_profile_id,
                    granted_by_id=granted_by,
                    is_active=True,
                )
                db.add(brand_grant)
                await log_action(
                    db=db,
                    action=ACCESS_GRANT_CREATED,
                    entity_type="user_access_grant",
                    entity_id=str(brand_grant.id),
                    actor_type=ActorType.USER,
                    actor_id=actor.id,
                    actor_email=actor.email,
                    actor_name=actor.name,
                    after_state={
                        "user_id": str(payload.user_id),
                        "scope": GrantScope.BRAND,
                        "brand_id": str(site.brand_id),
                        "access_profile_id": str(payload.access_profile_id),
                        "auto_created": True,
                    },
                )
                log.info(
                    "access_grant.brand.auto_created",
                    user_id=str(payload.user_id),
                    brand_id=str(site.brand_id),
                )

            # Group-scope grant — upsert only if no active group grant exists
            brand_r2 = await db.execute(select(Brand).where(Brand.id == site.brand_id))
            brand = brand_r2.scalar_one_or_none()
            if brand:
                group_dup_r = await db.execute(
                    select(UserAccessGrant).where(
                        UserAccessGrant.user_id == payload.user_id,
                        UserAccessGrant.scope == GrantScope.GROUP,
                        UserAccessGrant.group_id == brand.group_id,
                        UserAccessGrant.is_active == True,  # noqa: E712
                    )
                )
                if not group_dup_r.scalar_one_or_none():
                    group_grant = UserAccessGrant(
                        id=uuid.uuid4(),
                        user_id=payload.user_id,
                        scope=GrantScope.GROUP,
                        group_id=brand.group_id,
                        access_profile_id=payload.access_profile_id,
                        granted_by_id=granted_by,
                        is_active=True,
                    )
                    db.add(group_grant)
                    await log_action(
                        db=db,
                        action=ACCESS_GRANT_CREATED,
                        entity_type="user_access_grant",
                        entity_id=str(group_grant.id),
                        actor_type=ActorType.USER,
                        actor_id=actor.id,
                        actor_email=actor.email,
                        actor_name=actor.name,
                        after_state={
                            "user_id": str(payload.user_id),
                            "scope": GrantScope.GROUP,
                            "group_id": str(brand.group_id),
                            "access_profile_id": str(payload.access_profile_id),
                            "auto_created": True,
                        },
                    )
                    log.info(
                        "access_grant.group.auto_created",
                        user_id=str(payload.user_id),
                        group_id=str(brand.group_id),
                    )

    await db.commit()
    await db.refresh(grant)

    log.info(
        "access_grant.created",
        grant_id=str(grant.id),
        user_id=str(payload.user_id),
        scope=payload.scope,
    )
    return grant


async def _assert_create_authority(
    db: AsyncSession,
    access: ManagementAccess,
    payload: AccessGrantCreate,
) -> None:
    """
    Enforce that the management user has authority to create this grant.

    Group-scope → can create site or brand-scope grants within their group.
    Brand-scope → can create site-scope grants within their brand.
    Site-scope  → cannot create any grant.

    Args:
        db: Active session.
        access: The caller's management access context.
        payload: The grant creation request.

    Raises:
        HTTPException: 403 if the caller lacks the authority.
    """
    caller_scope = access.scope

    if caller_scope == GrantScope.SITE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Site-scope users cannot create access grants",
        )

    if caller_scope == GrantScope.BRAND:
        if payload.scope != GrantScope.SITE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Brand-scope users can only create site-scope grants",
            )
        # Verify the site is within the caller's brand
        if payload.site_id:
            site_r = await db.execute(select(Site).where(Site.id == payload.site_id))
            site = site_r.scalar_one_or_none()
            if not site or site.brand_id != access.brand.id:  # type: ignore[union-attr]
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Site is not within your brand",
                )

    elif caller_scope == GrantScope.GROUP:
        if payload.scope == GrantScope.GROUP:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Group-scope users cannot create group-scope grants",
            )
        group_id = access.group.id  # type: ignore[union-attr]

        if payload.scope == GrantScope.BRAND and payload.brand_id:
            brand_r = await db.execute(select(Brand).where(Brand.id == payload.brand_id))
            brand = brand_r.scalar_one_or_none()
            if not brand or brand.group_id != group_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Brand is not within your group",
                )
        elif payload.scope == GrantScope.SITE and payload.site_id:
            site_r = await db.execute(select(Site).where(Site.id == payload.site_id))
            site = site_r.scalar_one_or_none()
            if not site:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Site not found",
                )
            brand_r = await db.execute(select(Brand).where(Brand.id == site.brand_id))
            brand = brand_r.scalar_one_or_none()
            if not brand or brand.group_id != group_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Site is not within your group",
                )


# Rank ladder for the 5 ROLE_MODEL.md system roles, lowest to highest authority.
# A custom (non-system) profile's actual permission breadth is unknowable from
# its name alone, so it is conservatively ranked at the top non-Master tier —
# this is the safe direction on both sides of the ceiling check: it stops a
# lower-ranked grantor from assigning an unverified custom profile, and it caps
# a custom-profile holder's own delegation ceiling rather than under-ranking
# them and accidentally over-restricting a legitimately senior custom role.
_ROLE_RANK: dict[str, int] = {
    SystemAccessProfile.STAFF.value: 1,
    SystemAccessProfile.REPORTING_ONLY.value: 2,
    SystemAccessProfile.MANAGER.value: 3,
    SystemAccessProfile.ADMIN.value: 4,
    SystemAccessProfile.MASTER.value: 5,
}
_UNRANKED_PROFILE_RANK = _ROLE_RANK[SystemAccessProfile.ADMIN.value]


def _role_rank(profile_name: str) -> int:
    """
    Resolve an access profile's rank in the delegation ceiling ladder.

    Args:
        profile_name: The AccessProfile.name value (system role name or a
            brand admin's custom profile name).

    Returns:
        int: Higher means more authority. Unrecognised (custom) names rank
            just below Master User — see _ROLE_RANK's comment for why.
    """
    return _ROLE_RANK.get(profile_name, _UNRANKED_PROFILE_RANK)


def _assert_not_master_profile(profile: AccessProfile) -> None:
    """
    Raise HTTP 403 if the profile being granted is the Master User tier.

    Master User is auto-created exactly once per site by
    site_service.create_site() and is immutable (ROLE_MODEL.md §2) — no
    caller, including a portal admin, may grant it through this service.

    Args:
        profile: The access profile the caller is attempting to grant.

    Raises:
        HTTPException: 403 if profile is the Master User system profile.
    """
    if profile.name == SystemAccessProfile.MASTER.value:
        log.warning("access_grant.create.master_profile_rejected", profile_id=str(profile.id))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master User access cannot be granted — it is fixed to its site",
        )


def _assert_role_ceiling(access: ManagementAccess, target_profile: AccessProfile) -> None:
    """
    Raise HTTP 403 if the target profile outranks the management caller's own.

    Implements the Stage 17 rule: "a user cannot grant a level of access
    higher than themself." The caller's rank comes from the access profile
    tied to the grant they authenticated with (access.access_profile).

    Args:
        access: The management caller's resolved access context.
        target_profile: The access profile being assigned to someone else.

    Raises:
        HTTPException: 403 if target_profile outranks the caller's own profile.
    """
    caller_rank = _role_rank(access.access_profile.name)
    target_rank = _role_rank(target_profile.name)
    if target_rank > caller_rank:
        log.warning(
            "access_grant.role_ceiling_rejected",
            caller_profile=access.access_profile.name,
            target_profile=target_profile.name,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot grant an access level higher than your own",
        )


async def _assert_not_master_user_grant(db: AsyncSession, grant: UserAccessGrant) -> None:
    """
    Raise HTTP 409 if the grant belongs to a Master User.

    Master User grants are auto-created with the site and must never be
    updated or revoked — that would risk locking a site out of its own
    fixed, full-access identity (ROLE_MODEL.md Master User role).

    Args:
        db: Active session.
        grant: The grant to check.

    Raises:
        HTTPException: 409 if the grant's user is a Master User.
    """
    user_r = await db.execute(select(User).where(User.id == grant.user_id))
    grant_user = user_r.scalar_one_or_none()
    if grant_user is not None and grant_user.is_master_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Master User's site grant cannot be modified or revoked",
        )


async def update_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    payload: AccessGrantUpdate,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> UserAccessGrant:
    """
    Update the POS access profile and/or backend role on an existing grant.

    Both fields are optional — only fields present in model_fields_set are
    written, so callers can update one or both independently.

    Args:
        db: Active session.
        grant_id: Grant to update.
        payload: Fields to update (access_profile_id and/or backend_role).
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.

    Returns:
        UserAccessGrant: The updated grant.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, superadmin)
    await _assert_not_master_user_grant(db, grant)

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    await _apply_grant_update(db, grant, payload, actor, management_access)

    await db.commit()
    await db.refresh(grant)

    log.info("access_grant.updated", grant_id=str(grant.id))
    return grant


async def _apply_grant_update(
    db: AsyncSession,
    grant: UserAccessGrant,
    payload: AccessGrantUpdate,
    actor: User | SuperAdmin,
    management_access: ManagementAccess | None,
) -> None:
    """
    Mutate a grant's profile and/or backend role and write the audit rows.

    Does NOT load/authorise the grant or commit — the caller owns those, so
    this can serve both a single update_grant() and a bulk operation that
    commits many grants in one transaction. Only fields present in
    payload.model_fields_set are touched (None on backend_role clears it).

    Args:
        db: Active session (no commit here).
        grant: The already-loaded, already-authorised grant to mutate.
        payload: Fields to update (access_profile_id and/or backend_role).
        actor: The caller, for audit attribution.
        management_access: Set for management callers (drives the role ceiling);
            None for portal admins, who bypass the ceiling.

    Raises:
        HTTPException: 404 unknown profile, 403 profile above the caller's
            ceiling or Master User, 422 bad backend_role, 409 backend access
            without email+password.
    """
    # Update POS access profile when explicitly supplied
    if "access_profile_id" in payload.model_fields_set and payload.access_profile_id is not None:
        profile_r = await db.execute(
            select(AccessProfile).where(
                AccessProfile.id == payload.access_profile_id,
                AccessProfile.is_active == True,  # noqa: E712
            )
        )
        new_profile = profile_r.scalar_one_or_none()
        if not new_profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access profile not found or inactive")

        _assert_not_master_profile(new_profile)
        if management_access:
            _assert_role_ceiling(management_access, new_profile)

        old_profile_id = grant.access_profile_id
        grant.access_profile_id = payload.access_profile_id

        await log_action(
            db=db,
            action=ACCESS_PROFILE_PORTAL_UPDATED,
            entity_type="user_access_grant",
            entity_id=str(grant.id),
            actor_type=ActorType.USER,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.name,
            before_state={"access_profile_id": str(old_profile_id)},
            after_state={"access_profile_id": str(payload.access_profile_id)},
        )

    # Update backend_role when explicitly supplied (None clears it)
    if "backend_role" in payload.model_fields_set:
        if payload.backend_role is not None and payload.backend_role not in _BACKEND_ROLES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"backend_role must be one of: {sorted(_BACKEND_ROLES)} or null",
            )
        if payload.backend_role is not None:
            # ROLE_MODEL.md §2 — email/password are only required once a
            # grant gives the user backend access.
            grant_user_r = await db.execute(select(User).where(User.id == grant.user_id))
            grant_user = grant_user_r.scalar_one_or_none()
            if grant_user is None or grant_user.email is None or grant_user.password_hash is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User must have an email and password before being granted backend access",
                )
        old_role = grant.backend_role
        grant.backend_role = payload.backend_role

        await log_action(
            db=db,
            action=ACCESS_GRANT_BACKEND_ROLE_UPDATED,
            entity_type="user_access_grant",
            entity_id=str(grant.id),
            actor_type=ActorType.USER,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.name,
            before_state={"backend_role": old_role},
            after_state={"backend_role": payload.backend_role},
        )


async def revoke_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> None:
    """
    Soft-delete a grant (set is_active=False).

    Args:
        db: Active session.
        grant_id: Grant to revoke.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, superadmin)
    await _assert_not_master_user_grant(db, grant)

    if not grant.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Grant is already revoked")

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    grant.is_active = False

    await log_action(
        db=db,
        action=ACCESS_GRANT_REVOKED,
        entity_type="user_access_grant",
        entity_id=str(grant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
    )
    await db.commit()

    log.info("access_grant.revoked", grant_id=str(grant.id))


async def set_default_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> UserAccessGrant:
    """
    Set a site-scope grant as the user's default (primary) login entry point.

    Clears is_default on all other active site-scope grants for the same user
    before setting is_default=True on the target grant. This ensures exactly
    one default at all times.

    Args:
        db: Active session.
        grant_id: Grant to make the default.
        management_access: Set for management JWT callers.
        superadmin: Set for portal admin callers.

    Returns:
        UserAccessGrant: The updated grant with is_default=True.

    Raises:
        HTTPException: 404 if grant not found or out of scope.
        HTTPException: 400 if the grant is not a site-scope grant.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, superadmin)

    if grant.scope != GrantScope.SITE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only site-scope grants can be set as default",
        )
    if not grant.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set a revoked grant as default",
        )

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    # Clear is_default on all other site-scope grants for this user
    other_defaults_r = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.user_id == grant.user_id,
            UserAccessGrant.scope == GrantScope.SITE,
            UserAccessGrant.is_active.is_(True),
            UserAccessGrant.is_default.is_(True),
            UserAccessGrant.id != grant_id,
        )
    )
    for other in other_defaults_r.scalars().all():
        other.is_default = False

    grant.is_default = True

    await log_action(
        db=db,
        action=ACCESS_GRANT_DEFAULT_SET,
        entity_type="user_access_grant",
        entity_id=str(grant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"user_id": str(grant.user_id), "site_id": str(grant.site_id)},
    )
    await db.commit()
    await db.refresh(grant)

    log.info("access_grant.default_set", grant_id=str(grant.id), user_id=str(grant.user_id))
    return grant


async def bulk_update_grants(
    db: AsyncSession,
    payload: AccessGrantBulkUpdate,
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> tuple[list[uuid.UUID], list[tuple[uuid.UUID, str]]]:
    """
    Apply one profile and/or backend-role change to many grants at once.

    Each grant is validated and mutated inside its own SAVEPOINT, so a grant
    that fails its scope, role-ceiling, Master-User, or backend-access check is
    rolled back and reported without aborting the grants that succeed. The whole
    batch commits once at the end (partial success).

    Args:
        db: Active session.
        payload: grant_ids plus the fields to apply (same presence semantics as
            AccessGrantUpdate — only keys present are written).
        management_access: Set for management callers (drives the role ceiling).
        superadmin: Set for portal admin callers.

    Returns:
        tuple: (succeeded grant ids, [(failed grant id, reason), ...]).

    Raises:
        HTTPException: 422 if neither updatable field was supplied.
    """
    # Reconstruct a per-grant update payload preserving which fields were set,
    # so _apply_grant_update touches exactly the same fields update_grant would.
    fields: dict[str, object] = {}
    if "access_profile_id" in payload.model_fields_set:
        fields["access_profile_id"] = payload.access_profile_id
    if "backend_role" in payload.model_fields_set:
        fields["backend_role"] = payload.backend_role
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nothing to update — supply access_profile_id and/or backend_role",
        )
    sub_payload = AccessGrantUpdate(**fields)

    actor = management_access.user if management_access else superadmin
    assert actor is not None

    succeeded: list[uuid.UUID] = []
    errors: list[tuple[uuid.UUID, str]] = []
    for grant_id in payload.grant_ids:
        try:
            # SAVEPOINT per grant → all-or-nothing for that grant even though a
            # single update mutates profile then backend_role in sequence.
            async with db.begin_nested():
                grant = await _load_grant_with_authority(db, grant_id, management_access, superadmin)
                await _assert_not_master_user_grant(db, grant)
                await _apply_grant_update(db, grant, sub_payload, actor, management_access)
            succeeded.append(grant_id)
        except HTTPException as exc:
            errors.append((grant_id, str(exc.detail)))

    if succeeded:
        await db.commit()

    log.info("access_grant.bulk_update", succeeded=len(succeeded), failed=len(errors))
    return succeeded, errors


async def bulk_revoke_grants(
    db: AsyncSession,
    grant_ids: list[uuid.UUID],
    management_access: ManagementAccess | None,
    superadmin: SuperAdmin | None,
) -> tuple[list[uuid.UUID], list[tuple[uuid.UUID, str]]]:
    """
    Revoke (soft-delete) many grants at once, skipping any the caller can't.

    Each grant is checked and revoked inside its own SAVEPOINT; a grant outside
    the caller's scope, already revoked, or belonging to a Master User is
    reported in errors rather than failing the whole batch.

    Args:
        db: Active session.
        grant_ids: The grants to revoke.
        management_access: Set for management callers.
        superadmin: Set for portal admin callers.

    Returns:
        tuple: (revoked grant ids, [(failed grant id, reason), ...]).
    """
    actor = management_access.user if management_access else superadmin
    assert actor is not None

    succeeded: list[uuid.UUID] = []
    errors: list[tuple[uuid.UUID, str]] = []
    for grant_id in grant_ids:
        try:
            async with db.begin_nested():
                grant = await _load_grant_with_authority(db, grant_id, management_access, superadmin)
                await _assert_not_master_user_grant(db, grant)
                if not grant.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, detail="Grant is already revoked"
                    )
                grant.is_active = False
                await log_action(
                    db=db,
                    action=ACCESS_GRANT_REVOKED,
                    entity_type="user_access_grant",
                    entity_id=str(grant.id),
                    actor_type=ActorType.USER,
                    actor_id=actor.id,
                    actor_email=actor.email,
                    actor_name=actor.name,
                )
            succeeded.append(grant_id)
        except HTTPException as exc:
            errors.append((grant_id, str(exc.detail)))

    if succeeded:
        await db.commit()

    log.info("access_grant.bulk_revoke", succeeded=len(succeeded), failed=len(errors))
    return succeeded, errors
