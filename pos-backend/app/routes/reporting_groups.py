"""Reporting Group management routes — list, create, rename, delete (Stage 16).

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list reporting groups (read-only); write operations
require a management or portal JWT, mirroring categories.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.reporting_group import ReportingGroupCreate, ReportingGroupOut, ReportingGroupUpdate
from app.services import reporting_group_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/reporting-groups", tags=["reporting-groups"])


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from reporting group write operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reporting group management requires a management or portal JWT",
        )


@router.get("", response_model=list[ReportingGroupOut], status_code=status.HTTP_200_OK)
async def list_reporting_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ReportingGroupOut]:
    """
    List reporting groups for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum number of reporting groups to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[ReportingGroupOut]: Reporting groups, default group first.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    groups = await reporting_group_service.list_reporting_groups(db, effective_brand_id, skip, limit)
    return [ReportingGroupOut.model_validate(g) for g in groups]


@router.post("", response_model=ReportingGroupOut, status_code=status.HTTP_201_CREATED)
async def create_reporting_group(
    payload: ReportingGroupCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ReportingGroupOut:
    """
    Create a new reporting group.

    Args:
        payload: Reporting group creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ReportingGroupOut: The created reporting group.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    group = await reporting_group_service.create_reporting_group(
        db, effective_brand_id, payload, access.actor_user
    )
    return ReportingGroupOut.model_validate(group)


@router.patch("/{reporting_group_id}", response_model=ReportingGroupOut, status_code=status.HTTP_200_OK)
async def update_reporting_group(
    reporting_group_id: uuid.UUID,
    payload: ReportingGroupUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ReportingGroupOut:
    """
    Rename a reporting group. The system default group cannot be renamed.

    Args:
        reporting_group_id: UUID of the reporting group to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ReportingGroupOut: The updated reporting group.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    group = await reporting_group_service.update_reporting_group(
        db, effective_brand_id, reporting_group_id, payload, access.actor_user
    )
    return ReportingGroupOut.model_validate(group)


@router.delete("/{reporting_group_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_reporting_group(
    reporting_group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a reporting group. Blocked for the default group or one still in use.

    Args:
        reporting_group_id: UUID of the reporting group to delete.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await reporting_group_service.delete_reporting_group(
        db, effective_brand_id, reporting_group_id, access.actor_user
    )
