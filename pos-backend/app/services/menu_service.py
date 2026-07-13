"""Business logic for Menus — saved, schedulable configurations distinct from a MenuLayout."""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    MENU_CREATED,
    MENU_DUPLICATED,
    MENU_PUBLISHED,
    MENU_SCHEDULE_CANCELLED,
    MENU_SCHEDULED,
    MENU_UPDATED,
)
from app.models.menu import Menu
from app.models.menu_layout import MenuLayout
from app.models.site import Site
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.schemas.menu import MenuCreate, MenuSchedule, MenuUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _validate_site(db: AsyncSession, brand_id: uuid.UUID, site_id: uuid.UUID) -> None:
    """Raise 400 if site_id does not belong to brand_id."""
    result = await db.execute(select(Site).where(Site.id == site_id, Site.brand_id == brand_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id does not belong to this brand")


async def _validate_menu_layout(db: AsyncSession, brand_id: uuid.UUID, menu_layout_id: uuid.UUID) -> None:
    """Raise 400 if menu_layout_id does not belong to brand_id."""
    result = await db.execute(select(MenuLayout).where(MenuLayout.id == menu_layout_id, MenuLayout.brand_id == brand_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="menu_layout_id does not belong to this brand")


async def _get_menu_or_404(db: AsyncSession, brand_id: uuid.UUID, menu_id: uuid.UUID) -> Menu:
    """Fetch a Menu scoped to a brand, or raise 404."""
    result = await db.execute(select(Menu).where(Menu.id == menu_id, Menu.brand_id == brand_id))
    menu = result.scalar_one_or_none()
    if menu is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    return menu


async def list_menus(
    db: AsyncSession,
    brand_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[Menu]:
    """Return menus for a brand, most recently updated first."""
    result = await db.execute(
        select(Menu).where(Menu.brand_id == brand_id).order_by(Menu.updated_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def create_menu(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: MenuCreate,
    actor: User | SuperAdmin,
) -> Menu:
    """
    Create a menu in 'draft' status.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to create the menu under.
        payload: Menu creation data.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        Menu: The created menu.

    Raises:
        HTTPException: 400 if scope='site' with a site_id from another brand,
            or if menu_layout_id does not belong to this brand.
    """
    if payload.scope == "site":
        if payload.site_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id is required when scope='site'")
        await _validate_site(db, brand_id, payload.site_id)
    if payload.menu_layout_id is not None:
        await _validate_menu_layout(db, brand_id, payload.menu_layout_id)

    menu = Menu(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=payload.site_id if payload.scope == "site" else None,
        scope=payload.scope,
        menu_layout_id=payload.menu_layout_id,
        name=payload.name,
        note=payload.note,
        status="draft",
    )
    db.add(menu)
    await db.flush()

    await log_action(
        db=db,
        action=MENU_CREATED,
        entity_type="menu",
        entity_id=str(menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": menu.name, "scope": menu.scope, "brand_id": str(brand_id)},
    )
    await db.commit()
    await db.refresh(menu)
    log.info("menu.created", menu_id=str(menu.id), brand_id=str(brand_id))
    return menu


async def update_menu(
    db: AsyncSession,
    brand_id: uuid.UUID,
    menu_id: uuid.UUID,
    payload: MenuUpdate,
    actor: User | SuperAdmin,
) -> Menu:
    """Update a menu's mutable fields."""
    menu = await _get_menu_or_404(db, brand_id, menu_id)

    before: dict = {}
    after: dict = {}
    if payload.name is not None:
        before["name"] = menu.name
        menu.name = payload.name
        after["name"] = payload.name
    if payload.note is not None:
        before["note"] = menu.note
        menu.note = payload.note
        after["note"] = payload.note
    if payload.menu_layout_id is not None:
        await _validate_menu_layout(db, brand_id, payload.menu_layout_id)
        before["menu_layout_id"] = str(menu.menu_layout_id) if menu.menu_layout_id else None
        menu.menu_layout_id = payload.menu_layout_id
        after["menu_layout_id"] = str(payload.menu_layout_id)
    if payload.scope is not None:
        if payload.scope == "site":
            site_id = payload.site_id if payload.site_id is not None else menu.site_id
            if site_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id is required when scope='site'")
            await _validate_site(db, brand_id, site_id)
            menu.site_id = site_id
        else:
            menu.site_id = None
        before["scope"] = menu.scope
        menu.scope = payload.scope
        after["scope"] = payload.scope

    await log_action(
        db=db,
        action=MENU_UPDATED,
        entity_type="menu",
        entity_id=str(menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(menu)
    return menu


async def duplicate_menu(db: AsyncSession, brand_id: uuid.UUID, menu_id: uuid.UUID, actor: User | SuperAdmin) -> Menu:
    """Duplicate a menu as a new draft (name suffixed "(copy)")."""
    source = await _get_menu_or_404(db, brand_id, menu_id)

    new_menu = Menu(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=source.site_id,
        scope=source.scope,
        menu_layout_id=source.menu_layout_id,
        name=f"{source.name} (copy)",
        note=source.note,
        status="draft",
    )
    db.add(new_menu)
    await db.flush()

    await log_action(
        db=db,
        action=MENU_DUPLICATED,
        entity_type="menu",
        entity_id=str(new_menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": new_menu.name, "duplicated_from": str(source.id)},
    )
    await db.commit()
    await db.refresh(new_menu)
    return new_menu


async def schedule_menu(
    db: AsyncSession,
    brand_id: uuid.UUID,
    menu_id: uuid.UUID,
    payload: MenuSchedule,
    actor: User | SuperAdmin,
) -> Menu:
    """
    Schedule a draft menu's publish for a future time.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        menu_id: UUID of the menu to schedule.
        payload: The target publish time.
        actor: The authenticated user performing the action.

    Returns:
        Menu: The menu, now status='scheduled'.

    Raises:
        HTTPException: 400 if the menu is already published, or the time is not in the future.
    """
    menu = await _get_menu_or_404(db, brand_id, menu_id)
    if menu.status == "published":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A published menu cannot be scheduled")
    if payload.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_at must be in the future")

    before = {"status": menu.status}
    menu.status = "scheduled"
    menu.scheduled_at = payload.scheduled_at

    await log_action(
        db=db,
        action=MENU_SCHEDULED,
        entity_type="menu",
        entity_id=str(menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"status": "scheduled", "scheduled_at": payload.scheduled_at.isoformat()},
    )
    await db.commit()
    await db.refresh(menu)
    return menu


async def cancel_menu_schedule(db: AsyncSession, brand_id: uuid.UUID, menu_id: uuid.UUID, actor: User | SuperAdmin) -> Menu:
    """Cancel a scheduled publish, reverting the menu to 'draft'."""
    menu = await _get_menu_or_404(db, brand_id, menu_id)
    if menu.status != "scheduled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Menu is not scheduled")

    menu.status = "draft"
    menu.scheduled_at = None

    await log_action(
        db=db,
        action=MENU_SCHEDULE_CANCELLED,
        entity_type="menu",
        entity_id=str(menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": "scheduled"},
        after_state={"status": "draft"},
    )
    await db.commit()
    await db.refresh(menu)
    return menu


async def publish_menu(db: AsyncSession, brand_id: uuid.UUID, menu_id: uuid.UUID, actor: User | SuperAdmin) -> Menu:
    """Publish a menu immediately (from 'draft' or 'scheduled')."""
    menu = await _get_menu_or_404(db, brand_id, menu_id)
    before = {"status": menu.status}
    menu.status = "published"
    menu.scheduled_at = None
    menu.published_at = datetime.now(timezone.utc)

    await log_action(
        db=db,
        action=MENU_PUBLISHED,
        entity_type="menu",
        entity_id=str(menu.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"status": "published"},
    )
    await db.commit()
    await db.refresh(menu)
    log.info("menu.published", menu_id=str(menu.id), brand_id=str(brand_id))
    return menu
