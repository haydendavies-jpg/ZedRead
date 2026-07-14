"""Access grant management routes — create, list, update, and revoke user grants.

These routes are used by the portal management UI for brand/site user management.
Accessible to management JWT users and portal admins. Both token types are
resolved via resolve_catalog_access; POS terminal JWTs are explicitly rejected
on write operations.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.constants.statuses import GrantScope
from app.database import get_db
from app.models.user import User
from app.schemas.access_grant import (
    AccessGrantBulkResult,
    AccessGrantBulkRevoke,
    AccessGrantBulkUpdate,
    AccessGrantCreate,
    AccessGrantResponse,
    AccessGrantUpdate,
    BulkGrantError,
)
from app.services import access_grant_service
from app.utils.dependencies import CatalogAccess, ManagementAccess, resolve_catalog_access

router = APIRouter(prefix="/access-grants", tags=["access-grants"])


@router.get("", response_model=list[AccessGrantResponse], status_code=status.HTTP_200_OK)
async def list_grants(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Filter by brand (required for portal/group-scope)"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[AccessGrantResponse]:
    """
    List active access grants within the caller's authority.

    Management users see grants within their scope (site/brand/group).
    Portal admins must supply brand_id to filter results.

    Args:
        skip: Pagination offset.
        limit: Maximum results.
        brand_id: Optional brand filter (required for portal admin).
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[AccessGrantResponse]: Active grants in scope.
    """
    grants = await access_grant_service.list_grants(
        db,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
        brand_id_param=brand_id,
        skip=skip,
        limit=limit,
    )

    # Batch-load the grants' users so the table can show who each grant belongs
    # to (name + login email/username + ref) without an N+1 per-row lookup.
    user_ids = {g.user_id for g in grants}
    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        users_r = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_by_id = {u.id: u for u in users_r.scalars().all()}

    responses: list[AccessGrantResponse] = []
    for g in grants:
        resp = AccessGrantResponse.model_validate(g)
        user = users_by_id.get(g.user_id)
        if user is not None:
            resp.user_name = user.name
            resp.user_email = user.email
            resp.user_ref = user.ref
        responses.append(resp)
    return responses


@router.post("", response_model=AccessGrantResponse, status_code=status.HTTP_201_CREATED)
async def create_grant(
    payload: AccessGrantCreate,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantResponse:
    """
    Create a new user access grant.

    Scope authority rules:
    - Group-scope users: can create brand-scope or site-scope grants within their group.
    - Brand-scope users: can create site-scope grants within their brand.
    - Site-scope users: cannot create grants (403).
    - Portal admins: can create any grant.

    Args:
        payload: Grant creation data (user_id, scope, entity FK, access_profile_id).
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        AccessGrantResponse: The created grant.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    grant = await access_grant_service.create_grant(
        db,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
        payload=payload,
    )
    return AccessGrantResponse.model_validate(grant)


@router.patch("/{grant_id}", response_model=AccessGrantResponse, status_code=status.HTTP_200_OK)
async def update_grant(
    grant_id: uuid.UUID,
    payload: AccessGrantUpdate,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantResponse:
    """
    Update the access profile on an existing grant.

    Args:
        grant_id: UUID of the grant to update.
        payload: New access_profile_id.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        AccessGrantResponse: The updated grant.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    grant = await access_grant_service.update_grant(
        db,
        grant_id=grant_id,
        payload=payload,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )
    return AccessGrantResponse.model_validate(grant)


@router.delete("/{grant_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(
    grant_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Revoke an access grant (soft-delete: set is_active=False).

    Args:
        grant_id: UUID of the grant to revoke.
        access: Resolved catalog access.
        db: Active database session.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    await access_grant_service.revoke_grant(
        db,
        grant_id=grant_id,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )


@router.post("/bulk-update", response_model=AccessGrantBulkResult, status_code=status.HTTP_200_OK)
async def bulk_update_grants(
    payload: AccessGrantBulkUpdate,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantBulkResult:
    """
    Apply one access-profile and/or backend-role change to many grants at once.

    Partial success: grants outside the caller's scope, above their role
    ceiling, or belonging to a Master User are reported in ``errors`` and the
    rest are applied.

    Args:
        payload: grant_ids plus the fields to apply.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        AccessGrantBulkResult: Which grants succeeded and which failed (with reasons).
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    succeeded, errors = await access_grant_service.bulk_update_grants(
        db,
        payload=payload,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )
    return AccessGrantBulkResult(
        succeeded=succeeded,
        errors=[BulkGrantError(grant_id=gid, detail=detail) for gid, detail in errors],
    )


@router.post("/bulk-revoke", response_model=AccessGrantBulkResult, status_code=status.HTTP_200_OK)
async def bulk_revoke_grants(
    payload: AccessGrantBulkRevoke,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantBulkResult:
    """
    Revoke (soft-delete) many grants at once.

    Partial success: grants outside the caller's scope, already revoked, or
    belonging to a Master User are reported in ``errors``; the rest are revoked.

    Args:
        payload: grant_ids to revoke.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        AccessGrantBulkResult: Which grants succeeded and which failed (with reasons).
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    succeeded, errors = await access_grant_service.bulk_revoke_grants(
        db,
        grant_ids=payload.grant_ids,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )
    return AccessGrantBulkResult(
        succeeded=succeeded,
        errors=[BulkGrantError(grant_id=gid, detail=detail) for gid, detail in errors],
    )


@router.post("/{grant_id}/set-default", response_model=AccessGrantResponse, status_code=status.HTTP_200_OK)
async def set_default_grant(
    grant_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantResponse:
    """
    Set a site-scope grant as the user's primary/default login entry point.

    Clears is_default on all other active site-scope grants for the same user.
    On next login, if the user has multiple portal-capable grants, the default
    grant is selected automatically without showing the scope-selection screen.

    Args:
        grant_id: UUID of the site-scope grant to make default.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        AccessGrantResponse: The updated grant with is_default=True.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant management requires a management or portal JWT",
        )
    grant = await access_grant_service.set_default_grant(
        db,
        grant_id=grant_id,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )
    return AccessGrantResponse.model_validate(grant)


# ── Access profiles listing (for portal admin UI + management delegation UI) ──

from app.models.access_profile import AccessProfile as AccessProfileModel
from app.models.brand import Brand as BrandModel
from app.schemas.access_profile import AccessProfileCapabilitiesUpdate
from pydantic import BaseModel

class AccessProfileOut(BaseModel):
    """Minimal access profile response for dropdowns."""
    id: uuid.UUID
    name: str
    is_system: bool
    can_access_portal: bool
    can_use_open_item: bool
    open_item_max_price_cents: int | None
    model_config = {"from_attributes": True}

profiles_router = APIRouter(prefix="/access-profiles", tags=["access-profiles"])


async def _assert_brand_in_management_scope(
    db: AsyncSession, mgmt_access: ManagementAccess, brand_id: uuid.UUID
) -> None:
    """
    Raise 403 if brand_id is outside a management caller's scope.

    Site/brand-scope callers may only list profiles for their own brand;
    group-scope callers may list profiles for any brand in their group.
    Stage 17 delegation UI needs this so the role-picker can be filtered to
    profiles the caller may actually grant, without leaking other brands'
    profile catalogs to a management JWT.

    Args:
        db: Active database session.
        mgmt_access: The management caller's resolved access context.
        brand_id: The brand_id requested in the query string.

    Raises:
        HTTPException: 403 if brand_id is outside the caller's scope.
    """
    if mgmt_access.scope in (GrantScope.SITE, GrantScope.BRAND):
        if mgmt_access.brand is None or mgmt_access.brand.id != brand_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand is outside your scope")
    elif mgmt_access.scope == GrantScope.GROUP:
        brand_r = await db.execute(select(BrandModel).where(BrandModel.id == brand_id))
        brand = brand_r.scalar_one_or_none()
        if brand is None or mgmt_access.group is None or brand.group_id != mgmt_access.group.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brand is outside your scope")


@profiles_router.get("", response_model=list[AccessProfileOut])
async def list_access_profiles(
    brand_id: str,
    skip: int = 0,
    limit: int = 200,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
):
    """List access profiles for a brand. Requires a management or portal JWT.

    Lazily seeds system profiles (Admin, Reporting Only, Manager, Staff) on first
    call for any brand that predates the seeding feature, so the dropdown is never
    empty even if the startup seed step did not run.

    Management callers (Stage 17) are restricted to brands within their own
    scope, so the portal's delegation UI can safely use this to populate a
    role-picker without exposing other brands' profile catalogs.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access profile listing requires a management or portal JWT",
        )
    if access.mgmt_access:
        await _assert_brand_in_management_scope(db, access.mgmt_access, uuid.UUID(brand_id))

    from app.services.access_profile_service import seed_system_profiles

    # Seed missing system profiles on demand so legacy brands always show profiles
    system_check = await db.execute(
        select(AccessProfileModel).where(
            AccessProfileModel.brand_id == brand_id,
            AccessProfileModel.is_system.is_(True),
        ).limit(1)
    )
    if system_check.scalar_one_or_none() is None:
        await seed_system_profiles(db, uuid.UUID(brand_id))
        await db.commit()

    result = await db.execute(
        select(AccessProfileModel)
        .where(AccessProfileModel.brand_id == brand_id, AccessProfileModel.is_active.is_(True))
        .offset(skip)
        .limit(limit)
        .order_by(AccessProfileModel.name)
    )
    return result.scalars().all()


# ── Page-category permission hierarchy (ROLE_MODEL.md §4) ────────────────────

from app.schemas.access_profile_page_permission import (
    PagePermissionGrant,
    PagePermissionsResponse,
    VisiblePagesResponse,
)
from app.services import access_profile_service


@profiles_router.get(
    "/{access_profile_id}/pages",
    response_model=PagePermissionsResponse,
    status_code=status.HTTP_200_OK,
)
async def list_page_permissions(
    access_profile_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PagePermissionsResponse:
    """
    List the page keys currently granted to an access profile.

    Args:
        access_profile_id: UUID of the profile to query.
        access: Resolved catalog access (any non-POS token type).
        db: Active database session.

    Returns:
        PagePermissionsResponse: The granted page keys.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Page permission management requires a management or portal JWT",
        )
    page_keys = await access_profile_service.list_page_permissions(db, access_profile_id)
    return PagePermissionsResponse(access_profile_id=access_profile_id, page_keys=page_keys)


@profiles_router.post(
    "/{access_profile_id}/pages",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def grant_page_permission(
    access_profile_id: uuid.UUID,
    payload: PagePermissionGrant,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Grant a single page to an access profile.

    Args:
        access_profile_id: UUID of the profile to grant the page to.
        payload: The page_key to grant.
        access: Resolved catalog access (any non-POS token type).
        db: Active database session.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Page permission management requires a management or portal JWT",
        )
    actor = access.mgmt_access.user if access.mgmt_access else access.portal_access
    assert actor is not None
    await access_profile_service.grant_page(db, access_profile_id, payload.page_key, actor)


@profiles_router.delete(
    "/{access_profile_id}/pages/{page_key}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_page_permission(
    access_profile_id: uuid.UUID,
    page_key: str,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Revoke a single page from an access profile.

    Args:
        access_profile_id: UUID of the profile to revoke the page from.
        page_key: The page key to revoke.
        access: Resolved catalog access (any non-POS token type).
        db: Active database session.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Page permission management requires a management or portal JWT",
        )
    actor = access.mgmt_access.user if access.mgmt_access else access.portal_access
    assert actor is not None
    await access_profile_service.revoke_page(db, access_profile_id, page_key, actor)


@profiles_router.get(
    "/{access_profile_id}/visible-pages",
    response_model=VisiblePagesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_visible_pages(
    access_profile_id: uuid.UUID,
    site_id: uuid.UUID = Query(..., description="Site whose license plan supplies the license gate"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> VisiblePagesResponse:
    """
    Resolve the pages visible to a profile at a site: role grant AND license gate.

    Args:
        access_profile_id: UUID of the profile to resolve pages for.
        site_id: UUID of the site whose license plan supplies the license gate.
        access: Resolved catalog access (any non-POS token type).
        db: Active database session.

    Returns:
        VisiblePagesResponse: Page keys visible under both gates.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Page permission management requires a management or portal JWT",
        )
    page_keys = await access_profile_service.resolve_visible_pages(db, access_profile_id, site_id)
    return VisiblePagesResponse(
        access_profile_id=access_profile_id,
        site_id=site_id,
        page_keys=sorted(page_keys),
    )


# ── Open-item capability flags (Stage 24) ─────────────────────────────────────


@profiles_router.patch(
    "/{access_profile_id}/capabilities",
    response_model=AccessProfileOut,
    status_code=status.HTTP_200_OK,
)
async def update_capabilities(
    access_profile_id: uuid.UUID,
    payload: AccessProfileCapabilitiesUpdate,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> AccessProfileOut:
    """
    Update an access profile's open-item capability flag and/or price ceiling.

    This is an action-permission capability, not a page grant, so it lives
    outside the page-permission hierarchy managed by the /pages routes above.

    Args:
        access_profile_id: UUID of the profile to update.
        payload: Fields to update — only fields explicitly set are written.
        access: Resolved catalog access (any non-POS token type).
        db: Active database session.

    Returns:
        AccessProfileOut: The updated profile.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access profile management requires a management or portal JWT",
        )
    actor = access.mgmt_access.user if access.mgmt_access else access.portal_access
    assert actor is not None
    profile = await access_profile_service.update_capabilities(db, access_profile_id, payload, actor)
    return AccessProfileOut.model_validate(profile)
