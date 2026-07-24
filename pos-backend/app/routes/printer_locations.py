"""Printer location management routes — list, create, and update printer locations.

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list (read-only, folded into GET /pos/print-config
instead — see routes/print_templates.py); writes require management/portal JWT.
All business logic lives in printer_location_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.printer_location import PrinterLocationCreate, PrinterLocationOut, PrinterLocationUpdate
from app.services import printer_location_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/printer-locations", tags=["printer-locations"])


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from printer-location write operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Printer location management requires a management or portal JWT",
        )


@router.get("", response_model=list[PrinterLocationOut], status_code=status.HTTP_200_OK)
async def list_printer_locations(
    include_inactive: bool = Query(False),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[PrinterLocationOut]:
    """
    List printer locations for the authenticated user's brand.

    Args:
        include_inactive: Include soft-deleted locations.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[PrinterLocationOut]: Locations ordered by name.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    locations = await printer_location_service.list_printer_locations(db, effective_brand_id, include_inactive)
    return [PrinterLocationOut.model_validate(loc) for loc in locations]


@router.post("", response_model=PrinterLocationOut, status_code=status.HTTP_201_CREATED)
async def create_printer_location(
    payload: PrinterLocationCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PrinterLocationOut:
    """
    Create a new printer location — its docket print template is auto-created with it.

    Args:
        payload: Printer location creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        PrinterLocationOut: The created location.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    location = await printer_location_service.create_printer_location(
        db, effective_brand_id, payload, access.actor_user
    )
    return PrinterLocationOut.model_validate(location)


@router.patch("/{location_id}", response_model=PrinterLocationOut, status_code=status.HTTP_200_OK)
async def update_printer_location(
    location_id: uuid.UUID,
    payload: PrinterLocationUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PrinterLocationOut:
    """
    Update a printer location's mutable fields (name, copy_count, is_active).

    Args:
        location_id: UUID of the printer location to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        PrinterLocationOut: The updated location.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    location = await printer_location_service.update_printer_location(
        db, effective_brand_id, location_id, payload, access.actor_user
    )
    return PrinterLocationOut.model_validate(location)
