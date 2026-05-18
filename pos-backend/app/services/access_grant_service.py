"""Business logic for POS user access grant management.

Scope enforcement rules:
  group-scope management user  → can create brand-scope or site-scope grants
                                  within their group
  brand-scope management user  → can create site-scope grants within their brand
  site-scope management user   → cannot create grants (read-only)
  portal admin                 → full authority (bypasses scope checks)
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    ACCESS_GRANT_BACKEND_ROLE_UPDATED,
    ACCESS_GRANT_CREATED,
    ACCESS_GRANT_DEFAULT_SET,
    ACCESS_GRANT_REVOKED,
    ACCESS_PROFILE_PORTAL_UPDATED,
)
from app.constants.statuses import ActorType, GrantScope
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.portal_user import PortalUser
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.schemas.access_grant import AccessGrantCreate, AccessGrantUpdate
from app.services.audit_service import log_action
from app.utils.dependencies import ManagementAccess

log = structlog.get_logger(__name__)


async def _load_grant_with_authority(
    db: AsyncSession,
    grant_id: uuid.UUID,
    management_access: ManagementAccess | None,
    portal_user: PortalUser | None,
) -> UserAccessGrant:
    """
    Load a grant and verify the caller has authority over it.

    Portal users have full authority. Management users must have the grant
    within their scope (site/brand/group boundary check).

    Args:
        db: Active session.
        grant_id: The grant to load.
        management_access: Set if caller is a management JWT user.
        portal_user: Set if caller is a portal admin.

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

    if portal_user:
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
    portal_user: PortalUser | None,
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
        portal_user: Set for portal admin callers.
        brand_id_param: Optional brand_id filter (required for portal/group-scope).
        skip: Pagination offset.
        limit: Maximum results.

    Returns:
        list[UserAccessGrant]: Matching grants.
    """
    query = select(UserAccessGrant).where(UserAccessGrant.is_active == True)  # noqa: E712

    if portal_user:
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


async def create_grant(
    db: AsyncSession,
    management_access: ManagementAccess | None,
    portal_user: PortalUser | None,
    payload: AccessGrantCreate,
) -> UserAccessGrant:
    """
    Create a new access grant, enforcing scope authority rules.

    Args:
        db: Active session.
        management_access: Set for management JWT callers.
        portal_user: Set for portal admin callers.
        payload: Grant creation data.

    Returns:
        UserAccessGrant: The created grant.

    Raises:
        HTTPException: 403 if the caller lacks authority for the requested scope.
        HTTPException: 404 if the target user or profile does not exist.
        HTTPException: 409 if an active grant already exists for the same user/scope/entity.
    """
    # Verify the target user exists and belongs to a brand in scope
    user_r = await db.execute(select(POSUser).where(POSUser.id == payload.user_id))
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

    # Enforce scope authority if the caller is a management user (not portal admin)
    if management_access:
        await _assert_create_authority(db, management_access, payload)

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

    actor = management_access.user if management_access else portal_user
    assert actor is not None

    granted_by = actor.id if isinstance(actor, POSUser) else None

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


_BACKEND_ROLES = {"admin", "users", "reporting"}


async def update_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    payload: AccessGrantUpdate,
    management_access: ManagementAccess | None,
    portal_user: PortalUser | None,
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
        portal_user: Set for portal admin callers.

    Returns:
        UserAccessGrant: The updated grant.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, portal_user)

    actor = management_access.user if management_access else portal_user
    assert actor is not None

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

    await db.commit()
    await db.refresh(grant)

    log.info("access_grant.updated", grant_id=str(grant.id))
    return grant


async def revoke_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    management_access: ManagementAccess | None,
    portal_user: PortalUser | None,
) -> None:
    """
    Soft-delete a grant (set is_active=False).

    Args:
        db: Active session.
        grant_id: Grant to revoke.
        management_access: Set for management JWT callers.
        portal_user: Set for portal admin callers.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, portal_user)

    if not grant.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Grant is already revoked")

    actor = management_access.user if management_access else portal_user
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
    portal_user: PortalUser | None,
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
        portal_user: Set for portal admin callers.

    Returns:
        UserAccessGrant: The updated grant with is_default=True.

    Raises:
        HTTPException: 404 if grant not found or out of scope.
        HTTPException: 400 if the grant is not a site-scope grant.
    """
    grant = await _load_grant_with_authority(db, grant_id, management_access, portal_user)

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

    actor = management_access.user if management_access else portal_user
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
