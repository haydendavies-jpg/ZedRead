"""Menus routes — saved, schedulable configurations distinct from a MenuLayout.

Management/portal JWT only, mirroring menu_layouts.py's access rule (a menu is
a management-authoring concept, not something a POS terminal reads directly).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.menu import MenuCreate, MenuOut, MenuSchedule, MenuUpdate
from app.services import menu_service
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/menus", tags=["menus"])


def _require_management(access: CatalogAccess) -> None:
    """Reject POS terminal tokens — Menus is a management-authoring concept."""
    if access.pos_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Menus require a management or portal JWT")


@router.get("", response_model=list[MenuOut], status_code=status.HTTP_200_OK)
async def list_brand_menus(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[MenuOut]:
    """
    List menus for the authenticated user's brand, most recently updated first.

    Args:
        skip: Pagination offset.
        limit: Maximum rows to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        list[MenuOut]: Menus for the brand.
    """
    _require_management(access)
    menus = await menu_service.list_menus(db, access.effective_brand_id(brand_id), skip, limit)
    return [MenuOut.model_validate(m) for m in menus]


@router.post("", response_model=MenuOut, status_code=status.HTTP_201_CREATED)
async def create_brand_menu(
    payload: MenuCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Create a menu in 'draft' status.

    Args:
        payload: Menu creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The created menu.
    """
    _require_management(access)
    menu = await menu_service.create_menu(db, access.effective_brand_id(brand_id), payload, access.actor_user)
    return MenuOut.model_validate(menu)


@router.patch("/{menu_id}", response_model=MenuOut, status_code=status.HTTP_200_OK)
async def update_brand_menu(
    menu_id: uuid.UUID,
    payload: MenuUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Update a menu's mutable fields.

    Args:
        menu_id: UUID of the menu to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The updated menu.
    """
    _require_management(access)
    menu = await menu_service.update_menu(db, access.effective_brand_id(brand_id), menu_id, payload, access.actor_user)
    return MenuOut.model_validate(menu)


@router.post("/{menu_id}/duplicate", response_model=MenuOut, status_code=status.HTTP_201_CREATED)
async def duplicate_brand_menu(
    menu_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Duplicate a menu as a new draft.

    Args:
        menu_id: UUID of the menu to duplicate.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The newly created copy.
    """
    _require_management(access)
    menu = await menu_service.duplicate_menu(db, access.effective_brand_id(brand_id), menu_id, access.actor_user)
    return MenuOut.model_validate(menu)


@router.post("/{menu_id}/schedule", response_model=MenuOut, status_code=status.HTTP_200_OK)
async def schedule_brand_menu(
    menu_id: uuid.UUID,
    payload: MenuSchedule,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Schedule a draft menu's publish for a future time.

    Args:
        menu_id: UUID of the menu to schedule.
        payload: The target publish time.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The menu, now status='scheduled'.
    """
    _require_management(access)
    menu = await menu_service.schedule_menu(db, access.effective_brand_id(brand_id), menu_id, payload, access.actor_user)
    return MenuOut.model_validate(menu)


@router.post("/{menu_id}/cancel-schedule", response_model=MenuOut, status_code=status.HTTP_200_OK)
async def cancel_brand_menu_schedule(
    menu_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Cancel a scheduled publish, reverting the menu to 'draft'.

    Args:
        menu_id: UUID of the menu.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The menu, now status='draft'.
    """
    _require_management(access)
    menu = await menu_service.cancel_menu_schedule(db, access.effective_brand_id(brand_id), menu_id, access.actor_user)
    return MenuOut.model_validate(menu)


@router.post("/{menu_id}/publish", response_model=MenuOut, status_code=status.HTTP_200_OK)
async def publish_brand_menu(
    menu_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> MenuOut:
    """
    Publish a menu immediately.

    Args:
        menu_id: UUID of the menu to publish.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (management or portal).
        db: Active database session.

    Returns:
        MenuOut: The menu, now status='published'.
    """
    _require_management(access)
    menu = await menu_service.publish_menu(db, access.effective_brand_id(brand_id), menu_id, access.actor_user)
    return MenuOut.model_validate(menu)
