"""Access grant management routes — create, list, update, and revoke user grants.

These routes are used by the portal management UI for brand/site user management.
Accessible to management JWT users and portal admins. Both token types are
resolved via resolve_catalog_access; POS terminal JWTs are explicitly rejected
on write operations.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.access_grant import AccessGrantCreate, AccessGrantResponse, AccessGrantUpdate
from app.services import access_grant_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

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
        portal_user=access.portal_access,
        brand_id_param=brand_id,
        skip=skip,
        limit=limit,
    )
    return [AccessGrantResponse.model_validate(g) for g in grants]


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
        portal_user=access.portal_access,
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
        portal_user=access.portal_access,
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
        portal_user=access.portal_access,
    )


# ── Access profiles listing (for portal admin UI) ─────────────────────────────

from app.models.access_profile import AccessProfile as AccessProfileModel
from pydantic import BaseModel
from sqlalchemy import select
from app.utils.dependencies import get_current_portal_user

class AccessProfileOut(BaseModel):
    """Minimal access profile response for dropdowns."""
    id: str
    name: str
    is_system: bool
    can_access_portal: bool
    model_config = {"from_attributes": True}

profiles_router = APIRouter(prefix="/access-profiles", tags=["access-profiles"])

@profiles_router.get("", response_model=list[AccessProfileOut])
async def list_access_profiles(
    brand_id: str,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """List access profiles for a brand. Requires portal JWT."""
    result = await db.execute(
        select(AccessProfileModel)
        .where(AccessProfileModel.brand_id == brand_id, AccessProfileModel.is_active == True)
        .offset(skip)
        .limit(limit)
        .order_by(AccessProfileModel.name)
    )
    return result.scalars().all()
