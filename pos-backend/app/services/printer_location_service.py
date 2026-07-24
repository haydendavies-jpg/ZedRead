"""Business logic for PrinterLocation CRUD operations.

create_printer_location() also creates the location's 'docket' PrintTemplate
(with a default element set) in the same transaction — every printer location
always has exactly one docket template, so the portal never has to route
through a separate "create template for this location" step.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    PRINTER_LOCATION_CREATED,
    PRINTER_LOCATION_DEACTIVATED,
    PRINTER_LOCATION_UPDATED,
)
from app.models.printer_location import PrinterLocation
from app.models.user import User
from app.schemas.printer_location import PrinterLocationCreate, PrinterLocationUpdate
from app.services.audit_service import log_action
from app.services.print_template_service import create_docket_template

log = structlog.get_logger(__name__)


async def list_printer_locations(
    db: AsyncSession, brand_id: uuid.UUID, include_inactive: bool = False
) -> list[PrinterLocation]:
    """
    List printer locations for a brand.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list printer locations for.
        include_inactive: When True, also return soft-deleted locations.

    Returns:
        list[PrinterLocation]: Locations ordered by name.
    """
    query = select(PrinterLocation).where(PrinterLocation.brand_id == brand_id).order_by(PrinterLocation.name)
    if not include_inactive:
        query = query.where(PrinterLocation.is_active == True)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, location_id: uuid.UUID) -> PrinterLocation:
    """
    Fetch a printer location by ID, scoped to the brand, or raise 404.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        location_id: UUID of the printer location to fetch.

    Returns:
        PrinterLocation: The found location.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(PrinterLocation).where(PrinterLocation.id == location_id, PrinterLocation.brand_id == brand_id)
    )
    location = result.scalar_one_or_none()
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Printer location not found")
    return location


async def create_printer_location(
    db: AsyncSession, brand_id: uuid.UUID, payload: PrinterLocationCreate, actor: User
) -> PrinterLocation:
    """
    Create a printer location and its docket print template in one transaction.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to create the location under.
        payload: Printer location creation data.
        actor: The authenticated user performing the action.

    Returns:
        PrinterLocation: The created location.
    """
    location = PrinterLocation(
        id=uuid.uuid4(),
        brand_id=brand_id,
        name=payload.name,
        copy_count=payload.copy_count,
        is_active=True,
    )
    db.add(location)
    await db.flush()  # Location must be in DB before the docket template's FK insert
    await create_docket_template(db, brand_id, location.id, location.name)

    await log_action(
        db=db,
        action=PRINTER_LOCATION_CREATED,
        entity_type="printer_location",
        entity_id=str(location.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": location.name, "copy_count": location.copy_count},
    )
    await db.commit()
    await db.refresh(location)
    log.info("printer_location.created", printer_location_id=str(location.id), brand_id=str(brand_id))
    return location


async def update_printer_location(
    db: AsyncSession,
    brand_id: uuid.UUID,
    location_id: uuid.UUID,
    payload: PrinterLocationUpdate,
    actor: User,
) -> PrinterLocation:
    """
    Update a printer location's mutable fields and write an audit log row.

    A location being deactivated (is_active=False) writes
    PRINTER_LOCATION_DEACTIVATED instead of PRINTER_LOCATION_UPDATED when
    that's the only field changing, matching category_service's precedent
    for a dedicated action on the soft-delete transition.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        location_id: UUID of the printer location to update.
        payload: Fields to update (all optional).
        actor: The authenticated user performing the action.

    Returns:
        PrinterLocation: The updated location.

    Raises:
        HTTPException: 404 if not found.
    """
    location = await _get_or_404(db, brand_id, location_id)

    before: dict = {}
    after: dict = {}
    if payload.name is not None:
        before["name"] = location.name
        location.name = payload.name
        after["name"] = payload.name
    if payload.copy_count is not None:
        before["copy_count"] = location.copy_count
        location.copy_count = payload.copy_count
        after["copy_count"] = payload.copy_count
    if payload.is_active is not None:
        before["is_active"] = location.is_active
        location.is_active = payload.is_active
        after["is_active"] = payload.is_active

    action = (
        PRINTER_LOCATION_DEACTIVATED
        if payload.is_active is False and len(after) == 1
        else PRINTER_LOCATION_UPDATED
    )
    await log_action(
        db=db,
        action=action,
        entity_type="printer_location",
        entity_id=str(location.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(location)
    return location
