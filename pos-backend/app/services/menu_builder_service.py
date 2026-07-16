"""Business logic for the POS Menu Builder (Stage 23; Phase 2 grid editor).

A MenuLayout is a named, graphical POS menu: a tree of MenuTab rows (nested
via parent_tab_id), each holding an ordered set of MenuButton rows. A button
is either kind='product' (references a product by its human-readable `ref`
code rather than a foreign key, so it survives the underlying product being
deleted and recreated with the same code) or kind='folder' (opens a nested
child MenuTab). Publishing a layout is a warn-don't-block operation: a
product button whose code no longer resolves to an active product is
reported back to the caller but does not stop the publish.
"""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    MENU_BUTTON_ADDED,
    MENU_BUTTON_BULK_RECOLORED,
    MENU_BUTTON_BULK_REMOVED,
    MENU_BUTTON_MOVED,
    MENU_BUTTON_REMOVED,
    MENU_BUTTON_REORDERED,
    MENU_BUTTON_UPDATED,
    MENU_LAYOUT_CREATED,
    MENU_LAYOUT_DELETED,
    MENU_LAYOUT_DUPLICATED,
    MENU_LAYOUT_PUBLISHED,
    MENU_LAYOUT_SCHEDULE_CANCELLED,
    MENU_LAYOUT_SCHEDULED,
    MENU_LAYOUT_UNPUBLISHED,
    MENU_LAYOUT_UPDATED,
    MENU_TAB_CREATED,
    MENU_TAB_DELETED,
    MENU_TAB_GROUPED,
    MENU_TAB_REORDERED,
    MENU_TAB_UPDATED,
)
from app.models.category import Category
from app.models.menu_button import MenuButton
from app.models.menu_layout import MenuLayout
from app.models.menu_tab import MenuTab
from app.models.product import Product
from app.models.site import Site
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.schemas.menu_layout import (
    MenuButtonCreate,
    MenuButtonOut,
    MenuButtonUpdate,
    MenuLayoutCreate,
    MenuLayoutUpdate,
    MenuTabCreate,
    MenuTabOut,
    MenuTabUpdate,
    PublishWarning,
)
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)

_PRODUCT_NOT_FOUND = "product_not_found"
_PRODUCT_INACTIVE = "product_inactive"


# ── Fetch helpers ─────────────────────────────────────────────────────────────


async def _get_layout_or_404(db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID) -> MenuLayout:
    """Fetch a MenuLayout by id scoped to a brand, or raise HTTP 404."""
    result = await db.execute(
        select(MenuLayout).where(MenuLayout.id == layout_id, MenuLayout.brand_id == brand_id)
    )
    layout = result.scalar_one_or_none()
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu layout not found")
    return layout


async def _get_tab_or_404(db: AsyncSession, layout_id: uuid.UUID, tab_id: uuid.UUID) -> MenuTab:
    """Fetch a MenuTab by id scoped to a layout, or raise HTTP 404."""
    result = await db.execute(select(MenuTab).where(MenuTab.id == tab_id, MenuTab.layout_id == layout_id))
    tab = result.scalar_one_or_none()
    if tab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu tab not found")
    return tab


async def _get_button_or_404(db: AsyncSession, tab_id: uuid.UUID, button_id: uuid.UUID) -> MenuButton:
    """Fetch a MenuButton by id scoped to a tab, or raise HTTP 404."""
    result = await db.execute(select(MenuButton).where(MenuButton.id == button_id, MenuButton.tab_id == tab_id))
    button = result.scalar_one_or_none()
    if button is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu button not found")
    return button


async def _resolve_products_by_ref(
    db: AsyncSession, brand_id: uuid.UUID, refs: set[str]
) -> dict[str, tuple[Product, str | None]]:
    """
    Look up a set of product ref codes within a brand in a single query.

    Args:
        db: Active database session.
        brand_id: The brand to scope the lookup to.
        refs: The set of product ref codes to resolve.

    Returns:
        dict[str, tuple[Product, str | None]]: Maps each resolved ref to its
            Product row plus its category's default_color (for the
            inspector's "Category default" reset / fallback tile fill).
            Refs with no matching product in this brand are simply absent.
    """
    if not refs:
        return {}
    result = await db.execute(
        select(Product, Category.default_color)
        .join(Category, Product.category_id == Category.id)
        .where(Product.brand_id == brand_id, Product.ref.in_(refs))
    )
    return {p.ref: (p, color) for p, color in result.all()}


async def _load_buttons_for_tabs(db: AsyncSession, tab_ids: list[uuid.UUID]) -> list[MenuButton]:
    """Load every button belonging to any of the given tabs, ordered by display_order."""
    if not tab_ids:
        return []
    result = await db.execute(
        select(MenuButton).where(MenuButton.tab_id.in_(tab_ids)).order_by(MenuButton.display_order)
    )
    return list(result.scalars().all())


def _build_button_out(
    button: MenuButton,
    product_by_ref: dict[str, tuple[Product, str | None]],
    tabs_by_id: dict[uuid.UUID, MenuTab],
    button_count_by_tab: dict[uuid.UUID, int],
) -> MenuButtonOut:
    """Combine a stored MenuButton row with its resolved product or child-tab preview."""
    if button.kind == "folder":
        child = tabs_by_id.get(button.child_tab_id) if button.child_tab_id else None
        return MenuButtonOut(
            id=button.id,
            tab_id=button.tab_id,
            kind=button.kind,
            product_ref=None,
            child_tab_id=button.child_tab_id,
            width=button.width,
            height=button.height,
            color=button.color,
            display_order=button.display_order,
            grid_col=button.grid_col,
            grid_row=button.grid_row,
            child_tab_name=child.name if child else None,
            child_tab_button_count=button_count_by_tab.get(button.child_tab_id, 0) if button.child_tab_id else None,
        )

    resolved = product_by_ref.get(button.product_ref) if button.product_ref else None
    product, category_color = resolved if resolved else (None, None)
    return MenuButtonOut(
        id=button.id,
        tab_id=button.tab_id,
        kind=button.kind,
        product_ref=button.product_ref,
        child_tab_id=None,
        width=button.width,
        height=button.height,
        color=button.color,
        display_order=button.display_order,
        grid_col=button.grid_col,
        grid_row=button.grid_row,
        product_name=product.name if product else None,
        price_cents=product.base_price_cents if product else None,
        is_active=product.is_active if product else None,
        category_color=category_color,
    )


async def _resolve_buttons_out(
    db: AsyncSession, brand_id: uuid.UUID, buttons: list[MenuButton]
) -> list[MenuButtonOut]:
    """
    Build full MenuButtonOut responses for an explicit, small list of buttons.

    Used by mutation endpoints that only touch a handful of buttons (bulk
    recolor, single-button placement) so they can hand the frontend a fully
    resolved cache-patch without paying for _load_tabs_with_buttons' whole-
    layout scan and catalog resolution.

    Args:
        db: Active database session.
        brand_id: Brand the buttons' products must resolve against.
        buttons: The specific buttons to resolve (assumed already committed/refreshed).

    Returns:
        list[MenuButtonOut]: One resolved entry per input button, same order.
    """
    product_refs = {b.product_ref for b in buttons if b.kind == "product" and b.product_ref}
    products_by_ref = await _resolve_products_by_ref(db, brand_id, product_refs)

    # Only folder-kind buttons need their child tab's name/button-count preview resolved.
    child_tab_ids = [b.child_tab_id for b in buttons if b.kind == "folder" and b.child_tab_id]
    tabs_by_id: dict[uuid.UUID, MenuTab] = {}
    button_count_by_tab: dict[uuid.UUID, int] = {}
    if child_tab_ids:
        tabs_result = await db.execute(select(MenuTab).where(MenuTab.id.in_(child_tab_ids)))
        tabs_by_id = {t.id: t for t in tabs_result.scalars().all()}
        counts_result = await db.execute(
            select(MenuButton.tab_id, func.count(MenuButton.id))
            .where(MenuButton.tab_id.in_(child_tab_ids))
            .group_by(MenuButton.tab_id)
        )
        button_count_by_tab = dict(counts_result.all())

    return [_build_button_out(b, products_by_ref, tabs_by_id, button_count_by_tab) for b in buttons]


async def _load_all_tabs(db: AsyncSession, layout_id: uuid.UUID) -> list[MenuTab]:
    """Load every tab (any nesting depth) belonging to a layout, ordered by display_order."""
    result = await db.execute(
        select(MenuTab).where(MenuTab.layout_id == layout_id).order_by(MenuTab.display_order)
    )
    return list(result.scalars().all())


async def _load_tabs_with_buttons(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID
) -> list[MenuTabOut]:
    """
    Load every tab in a layout (flat, any nesting depth) with its ordered, resolved buttons.

    Args:
        db: Active database session.
        brand_id: The brand the layout's products must resolve against.
        layout_id: The layout to load tabs for.

    Returns:
        list[MenuTabOut]: Every tab, each with buttons ordered by
            display_order and resolved against the brand's catalog. The
            frontend builds the rail (parent_tab_id is None) and breadcrumb
            (walking parent_tab_id) from this flat list.
    """
    tabs = await _load_all_tabs(db, layout_id)
    tabs_by_id = {t.id: t for t in tabs}

    buttons = await _load_buttons_for_tabs(db, [t.id for t in tabs])
    product_refs = {b.product_ref for b in buttons if b.product_ref}
    products_by_ref = await _resolve_products_by_ref(db, brand_id, product_refs)

    button_count_by_tab: dict[uuid.UUID, int] = {}
    buttons_by_tab: dict[uuid.UUID, list[MenuButton]] = {}
    for b in buttons:
        buttons_by_tab.setdefault(b.tab_id, []).append(b)
        button_count_by_tab[b.tab_id] = button_count_by_tab.get(b.tab_id, 0) + 1

    return [
        MenuTabOut(
            id=t.id,
            layout_id=t.layout_id,
            parent_tab_id=t.parent_tab_id,
            name=t.name,
            color=t.color,
            display_order=t.display_order,
            buttons=[
                _build_button_out(b, products_by_ref, tabs_by_id, button_count_by_tab)
                for b in buttons_by_tab.get(t.id, [])
            ],
        )
        for t in tabs
    ]


# ── Layout CRUD ───────────────────────────────────────────────────────────────


async def list_menu_layouts(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 200,
) -> list[tuple[MenuLayout, int]]:
    """
    List menu layouts for a brand, optionally filtered to one site's scope.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list layouts for.
        site_id: If given, only include brand-wide layouts and layouts scoped to this site.
        skip: Pagination offset.
        limit: Maximum number of layouts to return.

    Returns:
        list[tuple[MenuLayout, int]]: Layouts ordered by name, each paired
            with its total button count (across every tab) for the list
            view's "N buttons" caption.
    """
    button_count_subq = (
        select(func.count(MenuButton.id))
        .join(MenuTab, MenuButton.tab_id == MenuTab.id)
        .where(MenuTab.layout_id == MenuLayout.id)
        .correlate(MenuLayout)
        .scalar_subquery()
    )
    query = select(MenuLayout, button_count_subq).where(MenuLayout.brand_id == brand_id)
    if site_id is not None:
        query = query.where((MenuLayout.scope == "brand") | (MenuLayout.site_id == site_id))
    query = query.order_by(MenuLayout.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return [(layout, count) for layout, count in result.all()]


async def get_menu_layout_detail(db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID) -> dict:
    """
    Fetch a menu layout with its tabs and resolved buttons.

    Returns:
        dict: Keys 'layout' (MenuLayout) and 'tabs' (list[MenuTabOut]).

    Raises:
        HTTPException: 404 if not found.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)
    tabs = await _load_tabs_with_buttons(db, brand_id, layout_id)
    return {"layout": layout, "tabs": tabs}


async def _validate_site(db: AsyncSession, brand_id: uuid.UUID, site_id: uuid.UUID) -> None:
    """Raise 400 if site_id does not belong to brand_id."""
    site_result = await db.execute(select(Site).where(Site.id == site_id, Site.brand_id == brand_id))
    if site_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id does not belong to this brand")


async def create_menu_layout(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: MenuLayoutCreate,
    actor: User | SuperAdmin,
) -> MenuLayout:
    """
    Create a new menu layout.

    Raises:
        HTTPException: 400 if scope='site' with a site_id from another brand.
    """
    if payload.scope == "site":
        if payload.site_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id is required when scope='site'")
        await _validate_site(db, brand_id, payload.site_id)

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=payload.site_id if payload.scope == "site" else None,
        scope=payload.scope,
        name=payload.name,
        color=payload.color,
        is_published=False,
        version=1,
    )
    db.add(layout)
    await db.flush()

    await log_action(
        db=db,
        action=MENU_LAYOUT_CREATED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": layout.name, "scope": layout.scope, "brand_id": str(brand_id)},
    )
    await db.commit()
    await db.refresh(layout)
    log.info("menu_layout.created", menu_layout_id=str(layout.id), brand_id=str(brand_id))
    return layout


async def update_menu_layout(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    payload: MenuLayoutUpdate,
    actor: User | SuperAdmin,
) -> MenuLayout:
    """
    Update a menu layout's mutable fields, including active-time/day-of-week scheduling.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 400 if is_all_day=False without both start_time and end_time.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)

    before: dict = {}
    after: dict = {}
    for field in ("name", "color"):
        value = getattr(payload, field)
        if value is not None:
            before[field] = getattr(layout, field)
            setattr(layout, field, value)
            after[field] = value

    if payload.is_all_day is not None:
        before["is_all_day"] = layout.is_all_day
        layout.is_all_day = payload.is_all_day
        after["is_all_day"] = payload.is_all_day
    if payload.start_time is not None:
        layout.start_time = payload.start_time
        after["start_time"] = payload.start_time.isoformat()
    if payload.end_time is not None:
        layout.end_time = payload.end_time
        after["end_time"] = payload.end_time.isoformat()
    if payload.active_days is not None:
        layout.active_days = payload.active_days
        after["active_days"] = payload.active_days

    if layout.is_all_day is False and (layout.start_time is None or layout.end_time is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time and end_time are required when is_all_day=False",
        )

    await log_action(
        db=db,
        action=MENU_LAYOUT_UPDATED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(layout)
    return layout


async def delete_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> None:
    """Delete a menu layout and its tabs/buttons (cascade)."""
    layout = await _get_layout_or_404(db, brand_id, layout_id)

    await log_action(
        db=db,
        action=MENU_LAYOUT_DELETED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"name": layout.name, "was_published": layout.is_published},
    )
    await db.delete(layout)
    await db.commit()
    log.info("menu_layout.deleted", menu_layout_id=str(layout_id), brand_id=str(brand_id))


async def duplicate_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> MenuLayout:
    """
    Duplicate a layout and its full tab tree + buttons (name suffixed "(copy)").

    The copy starts unpublished with no scheduling, regardless of the source.

    Raises:
        HTTPException: 404 if not found.
    """
    source = await _get_layout_or_404(db, brand_id, layout_id)
    source_tabs = await _load_all_tabs(db, layout_id)
    source_buttons = await _load_buttons_for_tabs(db, [t.id for t in source_tabs])

    new_layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=source.site_id,
        scope=source.scope,
        name=f"{source.name} (copy)",
        color=source.color,
        is_published=False,
        version=1,
        is_all_day=source.is_all_day,
        start_time=source.start_time,
        end_time=source.end_time,
        active_days=list(source.active_days),
    )
    db.add(new_layout)
    await db.flush()

    # Two passes: create every tab first (so folder buttons in pass two can
    # point at the new sibling tab's id, however parent/child order fell).
    tab_id_map: dict[uuid.UUID, uuid.UUID] = {}
    new_tabs: list[MenuTab] = []
    for tab in source_tabs:
        new_tab = MenuTab(id=uuid.uuid4(), layout_id=new_layout.id, name=tab.name, color=tab.color, display_order=tab.display_order)
        tab_id_map[tab.id] = new_tab.id
        new_tabs.append(new_tab)
        db.add(new_tab)
    await db.flush()
    for tab, new_tab in zip(source_tabs, new_tabs):
        new_tab.parent_tab_id = tab_id_map.get(tab.parent_tab_id) if tab.parent_tab_id else None

    for button in source_buttons:
        db.add(
            MenuButton(
                id=uuid.uuid4(),
                tab_id=tab_id_map[button.tab_id],
                kind=button.kind,
                product_ref=button.product_ref,
                child_tab_id=tab_id_map.get(button.child_tab_id) if button.child_tab_id else None,
                width=button.width,
                height=button.height,
                color=button.color,
                display_order=button.display_order,
            )
        )

    await log_action(
        db=db,
        action=MENU_LAYOUT_DUPLICATED,
        entity_type="menu_layout",
        entity_id=str(new_layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": new_layout.name, "duplicated_from": str(source.id)},
    )
    await db.commit()
    await db.refresh(new_layout)
    return new_layout


async def publish_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> tuple[MenuLayout, list[PublishWarning]]:
    """
    Publish a menu layout, bumping its version. Does not block on stale button refs.

    A button whose product_ref no longer resolves to an active product in the
    brand is reported as a warning rather than failing the publish — per the
    stage plan's "warn (don't silently fail)" requirement.

    Raises:
        HTTPException: 404 if not found.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)

    tabs = await _load_all_tabs(db, layout_id)
    tabs_by_id = {t.id: t for t in tabs}
    buttons = await _load_buttons_for_tabs(db, list(tabs_by_id.keys()))
    product_refs = {b.product_ref for b in buttons if b.kind == "product" and b.product_ref}
    products_by_ref = await _resolve_products_by_ref(db, brand_id, product_refs)

    warnings: list[PublishWarning] = []
    for button in buttons:
        if button.kind != "product":
            continue
        resolved = products_by_ref.get(button.product_ref)
        if resolved is None:
            warnings.append(
                PublishWarning(
                    button_id=button.id, tab_name=tabs_by_id[button.tab_id].name, product_ref=button.product_ref, reason=_PRODUCT_NOT_FOUND
                )
            )
        elif not resolved[0].is_active:
            warnings.append(
                PublishWarning(
                    button_id=button.id, tab_name=tabs_by_id[button.tab_id].name, product_ref=button.product_ref, reason=_PRODUCT_INACTIVE
                )
            )

    layout.is_published = True
    layout.version += 1
    layout.published_at = datetime.now(timezone.utc)
    layout.scheduled_publish_at = None

    await log_action(
        db=db,
        action=MENU_LAYOUT_PUBLISHED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"version": layout.version, "warning_count": len(warnings)},
    )
    await db.commit()
    await db.refresh(layout)
    log.info("menu_layout.published", menu_layout_id=str(layout.id), warning_count=len(warnings))
    return layout, warnings


async def unpublish_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> MenuLayout:
    """Unpublish a menu layout."""
    layout = await _get_layout_or_404(db, brand_id, layout_id)
    layout.is_published = False

    await log_action(
        db=db,
        action=MENU_LAYOUT_UNPUBLISHED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"is_published": False},
    )
    await db.commit()
    await db.refresh(layout)
    return layout


async def schedule_layout_publish(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, scheduled_publish_at: datetime, actor: User | SuperAdmin
) -> MenuLayout:
    """
    Set a layout's "Schedule publish" target time (bulk-publish-changes-later).

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 400 if scheduled_publish_at is not in the future.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)
    if scheduled_publish_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_publish_at must be in the future")

    layout.scheduled_publish_at = scheduled_publish_at
    await log_action(
        db=db,
        action=MENU_LAYOUT_SCHEDULED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"scheduled_publish_at": scheduled_publish_at.isoformat()},
    )
    await db.commit()
    await db.refresh(layout)
    return layout


async def cancel_layout_scheduled_publish(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> MenuLayout:
    """Cancel a layout's pending "Schedule publish"."""
    layout = await _get_layout_or_404(db, brand_id, layout_id)
    layout.scheduled_publish_at = None

    await log_action(
        db=db,
        action=MENU_LAYOUT_SCHEDULE_CANCELLED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"scheduled_publish_at": None},
    )
    await db.commit()
    await db.refresh(layout)
    return layout


# ── Tab CRUD ──────────────────────────────────────────────────────────────────


async def create_menu_tab(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    payload: MenuTabCreate,
    actor: User | SuperAdmin,
) -> MenuTab:
    """
    Add a tab to a menu layout, appended after any existing sibling tabs.

    Raises:
        HTTPException: 404 if the layout (or parent_tab_id, if given) does not exist for this brand.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    if payload.parent_tab_id is not None:
        await _get_tab_or_404(db, layout_id, payload.parent_tab_id)

    max_order_result = await db.execute(
        select(MenuTab.display_order)
        .where(MenuTab.layout_id == layout_id, MenuTab.parent_tab_id == payload.parent_tab_id)
        .order_by(MenuTab.display_order.desc())
    )
    max_order = max_order_result.scalars().first()

    tab = MenuTab(
        id=uuid.uuid4(),
        layout_id=layout_id,
        parent_tab_id=payload.parent_tab_id,
        name=payload.name,
        color=payload.color,
        display_order=(max_order + 1) if max_order is not None else 0,
    )
    db.add(tab)
    await db.flush()

    await log_action(
        db=db,
        action=MENU_TAB_CREATED,
        entity_type="menu_tab",
        entity_id=str(tab.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"name": tab.name, "layout_id": str(layout_id), "parent_tab_id": str(payload.parent_tab_id) if payload.parent_tab_id else None},
    )
    await db.commit()
    await db.refresh(tab)
    return tab


async def update_menu_tab(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    payload: MenuTabUpdate,
    actor: User | SuperAdmin,
) -> MenuTab:
    """Update a menu tab's mutable fields (name/color)."""
    await _get_layout_or_404(db, brand_id, layout_id)
    tab = await _get_tab_or_404(db, layout_id, tab_id)

    before: dict = {}
    after: dict = {}
    if payload.name is not None:
        before["name"] = tab.name
        tab.name = payload.name
        after["name"] = payload.name
    if payload.color is not None:
        before["color"] = tab.color
        tab.color = payload.color
        after["color"] = payload.color

    await log_action(
        db=db,
        action=MENU_TAB_UPDATED,
        entity_type="menu_tab",
        entity_id=str(tab.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )
    await db.commit()
    await db.refresh(tab)
    return tab


async def delete_menu_tab(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, tab_id: uuid.UUID, actor: User | SuperAdmin
) -> None:
    """Delete a menu tab, its nested child tabs, and their buttons (cascade)."""
    await _get_layout_or_404(db, brand_id, layout_id)
    tab = await _get_tab_or_404(db, layout_id, tab_id)

    await log_action(
        db=db,
        action=MENU_TAB_DELETED,
        entity_type="menu_tab",
        entity_id=str(tab.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"name": tab.name},
    )
    await db.delete(tab)
    await db.commit()


async def reorder_menu_tabs(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_ids: list[uuid.UUID],
    actor: User | SuperAdmin,
) -> list[MenuTab]:
    """
    Reorder a set of sibling tabs — each id in tab_ids gets display_order = its list index.

    All tabs in tab_ids must share the same parent_tab_id (siblings) — the
    rail only ever reorders top-level tabs, and drilling into a folder only
    ever reorders that folder's own children.

    Raises:
        HTTPException: 404 if the layout or any tab_id does not belong to it.
        HTTPException: 400 if tab_ids mixes tabs from different parents.
    """
    await _get_layout_or_404(db, brand_id, layout_id)

    existing_result = await db.execute(
        select(MenuTab).where(MenuTab.layout_id == layout_id, MenuTab.id.in_(tab_ids))
    )
    existing_by_id = {t.id: t for t in existing_result.scalars().all()}

    missing = set(tab_ids) - set(existing_by_id.keys())
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more tab_ids not found in this layout")
    parents = {t.parent_tab_id for t in existing_by_id.values()}
    if len(parents) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tab_ids must all share the same parent tab")

    for index, tab_id in enumerate(tab_ids):
        existing_by_id[tab_id].display_order = index

    await log_action(
        db=db,
        action=MENU_TAB_REORDERED,
        entity_type="menu_layout",
        entity_id=str(layout_id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"reordered_tab_ids": [str(i) for i in tab_ids]},
    )
    await db.commit()
    return [existing_by_id[tab_id] for tab_id in tab_ids]


# ── Button CRUD ───────────────────────────────────────────────────────────────


async def create_menu_button(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    payload: MenuButtonCreate,
    actor: User | SuperAdmin,
) -> MenuButtonOut:
    """
    Add a button to a tab — a product tile, or a folder that creates a new nested tab.

    Raises:
        HTTPException: 404 if the layout or tab does not exist.
        HTTPException: 400 if kind='product' and product_ref does not resolve
            to an active product, or if a required field for the kind is missing.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)

    max_order_result = await db.execute(
        select(MenuButton.display_order).where(MenuButton.tab_id == tab_id).order_by(MenuButton.display_order.desc())
    )
    max_order = max_order_result.scalars().first()
    display_order = (max_order + 1) if max_order is not None else 0

    if payload.kind == "folder":
        if not payload.name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required when kind='folder'")
        child_tab = MenuTab(id=uuid.uuid4(), layout_id=layout_id, parent_tab_id=tab_id, name=payload.name, color=payload.color, display_order=0)
        db.add(child_tab)
        await db.flush()
        button = MenuButton(
            id=uuid.uuid4(), tab_id=tab_id, kind="folder", child_tab_id=child_tab.id,
            width=payload.width, height=payload.height, color=payload.color, display_order=display_order,
        )
        after_state = {"kind": "folder", "child_tab_id": str(child_tab.id), "tab_id": str(tab_id)}
        product = None
        category_color = None
    else:
        child_tab = None
        if not payload.product_ref:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="product_ref is required when kind='product'")
        product_result = await db.execute(select(Product).where(Product.brand_id == brand_id, Product.ref == payload.product_ref))
        product = product_result.scalar_one_or_none()
        if product is None or not product.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="product_ref does not resolve to an active product in this brand")
        category_result = await db.execute(select(Category.default_color).where(Category.id == product.category_id))
        category_color = category_result.scalar_one_or_none()
        button = MenuButton(
            id=uuid.uuid4(), tab_id=tab_id, kind="product", product_ref=payload.product_ref,
            width=payload.width, height=payload.height, color=payload.color, display_order=display_order,
        )
        after_state = {"kind": "product", "product_ref": button.product_ref, "tab_id": str(tab_id)}

    db.add(button)
    await db.flush()

    await log_action(
        db=db, action=MENU_BUTTON_ADDED, entity_type="menu_button", entity_id=str(button.id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name, after_state=after_state,
    )
    await db.commit()
    await db.refresh(button)
    return _build_button_out(
        button,
        {payload.product_ref: (product, category_color)} if product else {},
        {child_tab.id: child_tab} if child_tab else {},
        {child_tab.id: 0} if child_tab else {},
    )


async def update_menu_button(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    button_id: uuid.UUID,
    payload: MenuButtonUpdate,
    actor: User | SuperAdmin,
) -> MenuButtonOut:
    """
    Update a button's mutable fields — resize (width/height), recolor, or relink a product.

    color is checked via model_fields_set (not `is not None`) so an explicit
    {"color": null} clears an override back to the linked product's category
    default colour (the inspector's "Category default" reset) — the same
    idiom used by access_grant_service.update_grant for backend_role.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 400 if product_ref is set on a folder button, or doesn't resolve.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)
    button = await _get_button_or_404(db, tab_id, button_id)

    before: dict = {}
    after: dict = {}
    if payload.product_ref is not None:
        if button.kind != "product":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot set product_ref on a folder button")
        product_result = await db.execute(select(Product).where(Product.brand_id == brand_id, Product.ref == payload.product_ref))
        product = product_result.scalar_one_or_none()
        if product is None or not product.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="product_ref does not resolve to an active product in this brand")
        before["product_ref"] = button.product_ref
        button.product_ref = payload.product_ref
        after["product_ref"] = payload.product_ref
    if payload.width is not None:
        before["width"] = button.width
        button.width = payload.width
        after["width"] = payload.width
    if payload.height is not None:
        before["height"] = button.height
        button.height = payload.height
        after["height"] = payload.height
    if "color" in payload.model_fields_set:
        before["color"] = button.color
        button.color = payload.color
        after["color"] = payload.color

    await log_action(
        db=db, action=MENU_BUTTON_UPDATED, entity_type="menu_button", entity_id=str(button.id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name, before_state=before, after_state=after,
    )
    await db.commit()
    await db.refresh(button)

    products_by_ref = {}
    if button.kind == "product" and button.product_ref:
        products_by_ref = await _resolve_products_by_ref(db, brand_id, {button.product_ref})
    return _build_button_out(button, products_by_ref, {}, {})


async def place_menu_button(
    db: AsyncSession,
    brand_id: uuid.UUID,
    button_id: uuid.UUID,
    tab_id: uuid.UUID,
    grid_col: int,
    grid_row: int,
    actor: User | SuperAdmin,
) -> MenuButtonOut:
    """
    Move a button to an explicit grid cell — the drag-to-any-cell operation.

    Unlike update_menu_button/reorder_menu_buttons (which take layout_id/tab_id
    from the URL path), this is addressed by button_id alone, so the button's
    current tab/layout is resolved via a join first (and used to authorize the
    move against brand_id and to validate the destination tab belongs to the
    same layout). On a cross-tab move, display_order is also bumped to the end
    of the destination tab's list, so a sane fallback order exists if
    grid_col/grid_row are ever cleared back to NULL.

    No overlap checking is performed against other buttons already occupying
    the destination cell — see MenuButtonPlace's docstring for why.

    Args:
        db: Active database session.
        brand_id: Brand to scope/authorize the move within.
        button_id: The button being moved.
        tab_id: Destination tab (may equal the button's current tab_id).
        grid_col: New 0-indexed column for the button's top-left cell.
        grid_row: New 0-indexed row for the button's top-left cell.
        actor: The authenticated user/superadmin performing the move.

    Returns:
        MenuButtonOut: The full, resolved button at its new position.

    Raises:
        HTTPException: 404 if the button (scoped to brand_id) or the
            destination tab_id (scoped to the button's own layout) is not found.
        HTTPException: 400 if grid_col + the button's stored width would
            exceed the 6-column grid.
    """
    # Resolve the button plus its current tab/layout in one join, scoped to
    # brand_id — this both authorizes the call and tells us which layout the
    # destination tab_id must belong to.
    result = await db.execute(
        select(MenuButton, MenuTab)
        .join(MenuTab, MenuButton.tab_id == MenuTab.id)
        .join(MenuLayout, MenuTab.layout_id == MenuLayout.id)
        .where(MenuButton.id == button_id, MenuLayout.brand_id == brand_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu button not found")
    button, current_tab = row

    # Destination tab must exist in the same layout the button already belongs to.
    await _get_tab_or_404(db, current_tab.layout_id, tab_id)

    if grid_col + button.width > 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="grid_col + width exceeds the 6-column grid")

    before = {"tab_id": str(button.tab_id), "grid_col": button.grid_col, "grid_row": button.grid_row}
    moved_to_new_tab = button.tab_id != tab_id
    button.tab_id = tab_id
    button.grid_col = grid_col
    button.grid_row = grid_row

    if moved_to_new_tab:
        # Keep a sane fallback order for this tab in case grid position is ever cleared.
        max_order_result = await db.execute(
            select(MenuButton.display_order).where(MenuButton.tab_id == tab_id).order_by(MenuButton.display_order.desc())
        )
        max_order = max_order_result.scalars().first()
        button.display_order = (max_order + 1) if max_order is not None else 0

    after = {"tab_id": str(tab_id), "grid_col": grid_col, "grid_row": grid_row}
    await log_action(
        db=db, action=MENU_BUTTON_MOVED, entity_type="menu_button", entity_id=str(button.id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name, before_state=before, after_state=after,
    )
    await db.commit()
    await db.refresh(button)

    resolved = await _resolve_buttons_out(db, brand_id, [button])
    return resolved[0]


async def delete_menu_button(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, tab_id: uuid.UUID, button_id: uuid.UUID, actor: User | SuperAdmin
) -> None:
    """Remove a button from a tab. A folder button's nested tab (and its buttons) cascade-deletes too."""
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)
    button = await _get_button_or_404(db, tab_id, button_id)

    await log_action(
        db=db, action=MENU_BUTTON_REMOVED, entity_type="menu_button", entity_id=str(button.id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        before_state={"kind": button.kind, "product_ref": button.product_ref, "tab_id": str(tab_id)},
    )
    if button.kind == "folder" and button.child_tab_id:
        child_tab = await db.get(MenuTab, button.child_tab_id)
        if child_tab is not None:
            await db.delete(child_tab)
    await db.delete(button)
    await db.commit()


async def reorder_menu_buttons(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    button_ids: list[uuid.UUID],
    actor: User | SuperAdmin,
) -> MenuTabOut:
    """
    Reorder a tab's buttons, and/or move buttons into this tab from another (drag-and-drop move).

    Every id in button_ids is (re)assigned to this tab_id and given
    display_order = its index in the list — a button dragged in from
    another tab only needs one call, against the destination tab.

    Raises:
        HTTPException: 404 if the layout, tab, or any button_id (scoped to the
            layout's other tabs) does not exist.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)

    layout_tabs_result = await db.execute(select(MenuTab.id).where(MenuTab.layout_id == layout_id))
    layout_tab_ids = [row[0] for row in layout_tabs_result.all()]

    buttons_result = await db.execute(select(MenuButton).where(MenuButton.tab_id.in_(layout_tab_ids)))
    buttons_by_id = {b.id: b for b in buttons_result.scalars().all()}

    missing = set(button_ids) - set(buttons_by_id.keys())
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more button_ids not found in this layout")

    for index, button_id in enumerate(button_ids):
        button = buttons_by_id[button_id]
        button.tab_id = tab_id
        button.display_order = index

    await log_action(
        db=db, action=MENU_BUTTON_REORDERED, entity_type="menu_tab", entity_id=str(tab_id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        after_state={"reordered_button_ids": [str(i) for i in button_ids]},
    )
    await db.commit()

    # Resolve only this tab's own buttons rather than reloading the whole
    # layout (_load_tabs_with_buttons) — this endpoint is called on every
    # drag-reorder, so scoping the reload to one tab matters for latency.
    tab = await _get_tab_or_404(db, layout_id, tab_id)
    tab_buttons = await _load_buttons_for_tabs(db, [tab_id])
    resolved_buttons = await _resolve_buttons_out(db, brand_id, tab_buttons)
    return MenuTabOut(
        id=tab.id,
        layout_id=tab.layout_id,
        parent_tab_id=tab.parent_tab_id,
        name=tab.name,
        color=tab.color,
        display_order=tab.display_order,
        buttons=resolved_buttons,
    )


async def _buttons_in_one_tab_or_400(db: AsyncSession, layout_id: uuid.UUID, button_ids: list[uuid.UUID]) -> tuple[uuid.UUID, list[MenuButton]]:
    """Fetch buttons by id (scoped to the layout), asserting they all share one source tab."""
    layout_tabs_result = await db.execute(select(MenuTab.id).where(MenuTab.layout_id == layout_id))
    layout_tab_ids = [row[0] for row in layout_tabs_result.all()]

    result = await db.execute(select(MenuButton).where(MenuButton.id.in_(button_ids), MenuButton.tab_id.in_(layout_tab_ids)))
    buttons = list(result.scalars().all())
    if len(buttons) != len(set(button_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more button_ids not found in this layout")

    tab_ids = {b.tab_id for b in buttons}
    if len(tab_ids) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="button_ids must all belong to the same tab")
    return tab_ids.pop(), buttons


async def bulk_recolor_menu_buttons(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, button_ids: list[uuid.UUID], color: str, actor: User | SuperAdmin
) -> list[MenuButtonOut]:
    """
    Bulk-recolor a multi-selection of buttons (the grid editor's floating action bar).

    Returns the full resolved buttons (not just their ids) so the frontend
    can patch its local cache in place instead of refetching the layout.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    _, buttons = await _buttons_in_one_tab_or_400(db, layout_id, button_ids)

    for button in buttons:
        button.color = color

    await log_action(
        db=db, action=MENU_BUTTON_BULK_RECOLORED, entity_type="menu_layout", entity_id=str(layout_id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        after_state={"button_ids": [str(b.id) for b in buttons], "color": color},
    )
    await db.commit()
    for button in buttons:
        await db.refresh(button)
    return await _resolve_buttons_out(db, brand_id, buttons)


async def bulk_delete_menu_buttons(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, button_ids: list[uuid.UUID], actor: User | SuperAdmin
) -> dict[str, list[uuid.UUID]]:
    """
    Bulk-delete a multi-selection of buttons (folder buttons' nested tabs cascade too).

    Returns:
        dict[str, list[uuid.UUID]]: 'deleted_button_ids' and 'deleted_tab_ids'
            (the cascaded nested tabs) so the frontend can drop both from its
            local cache without refetching the layout.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    _, buttons = await _buttons_in_one_tab_or_400(db, layout_id, button_ids)

    await log_action(
        db=db, action=MENU_BUTTON_BULK_REMOVED, entity_type="menu_layout", entity_id=str(layout_id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        before_state={"button_ids": [str(b.id) for b in buttons]},
    )
    deleted_button_ids = [b.id for b in buttons]
    child_tab_ids = [b.child_tab_id for b in buttons if b.kind == "folder" and b.child_tab_id]
    for button in buttons:
        await db.delete(button)
    if child_tab_ids:
        child_tabs_result = await db.execute(select(MenuTab).where(MenuTab.id.in_(child_tab_ids)))
        for child_tab in child_tabs_result.scalars().all():
            await db.delete(child_tab)
    await db.commit()
    return {"deleted_button_ids": deleted_button_ids, "deleted_tab_ids": child_tab_ids}


async def group_menu_buttons_into_tab(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, button_ids: list[uuid.UUID], name: str, actor: User | SuperAdmin
) -> MenuButtonOut:
    """
    Bundle a multi-selection of buttons into a newly created nested tab (the "Group into tab" bulk action).

    Creates a child tab under the buttons' shared source tab, moves the
    selected buttons into it, and leaves a single new folder button in the
    source tab pointing at it.

    Raises:
        HTTPException: 404 if the layout or any button_id doesn't exist.
        HTTPException: 400 if the buttons don't all share one source tab.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    source_tab_id, buttons = await _buttons_in_one_tab_or_400(db, layout_id, button_ids)

    child_tab = MenuTab(id=uuid.uuid4(), layout_id=layout_id, parent_tab_id=source_tab_id, name=name, color=None, display_order=0)
    db.add(child_tab)
    await db.flush()

    for index, button in enumerate(buttons):
        button.tab_id = child_tab.id
        button.display_order = index

    max_order_result = await db.execute(
        select(MenuButton.display_order).where(MenuButton.tab_id == source_tab_id).order_by(MenuButton.display_order.desc())
    )
    max_order = max_order_result.scalars().first()

    folder_button = MenuButton(
        id=uuid.uuid4(), tab_id=source_tab_id, kind="folder", child_tab_id=child_tab.id,
        width=2, height=2, display_order=(max_order + 1) if max_order is not None else 0,
    )
    db.add(folder_button)

    await log_action(
        db=db, action=MENU_TAB_GROUPED, entity_type="menu_tab", entity_id=str(child_tab.id),
        actor_id=actor.id, actor_email=actor.email, actor_name=actor.name,
        after_state={"name": name, "source_tab_id": str(source_tab_id), "button_ids": [str(b.id) for b in buttons]},
    )
    await db.commit()
    await db.refresh(folder_button)
    return _build_button_out(folder_button, {}, {child_tab.id: child_tab}, {child_tab.id: len(buttons)})


# ── POS consumption contract ──────────────────────────────────────────────────


def _layout_active_now(layout: MenuLayout) -> bool:
    """
    True if a layout's active-time/day-of-week window includes the current moment.

    Uses naive UTC "now" — sites don't carry a reliable IANA timezone today
    (Site.timezone is a free-form display string, not validated against
    zoneinfo), so this is a best-effort check pending that. Distinct from
    is_published, which the caller filters on separately.
    """
    if layout.is_all_day:
        return True
    now = datetime.now(timezone.utc)
    if now.weekday() not in layout.active_days:
        return False
    if layout.start_time is None or layout.end_time is None:
        return True
    return layout.start_time <= now.time() <= layout.end_time


async def get_published_menu_layouts_for_site(db: AsyncSession, site: Site) -> list[dict]:
    """
    Fetch every published, currently-active menu layout visible to a site.

    This is the read-only contract Android will eventually consume via
    GET /pos/menu-layout?site_id=. Android-side consumption is out of scope;
    only the contract is built. "Currently-active" applies each layout's own
    active-time/day-of-week window (distinct from is_published — see
    MenuLayout's docstring).

    Args:
        db: Active database session.
        site: The site to resolve visible published layouts for.

    Returns:
        list[dict]: Each dict has keys 'layout' (MenuLayout) and 'tabs' (list[MenuTabOut]).
    """
    result = await db.execute(
        select(MenuLayout).where(
            MenuLayout.brand_id == site.brand_id,
            MenuLayout.is_published == True,  # noqa: E712
            (MenuLayout.scope == "brand") | (MenuLayout.site_id == site.id),
        )
    )
    layouts = [layout for layout in result.scalars().all() if _layout_active_now(layout)]
    return [
        {"layout": layout, "tabs": await _load_tabs_with_buttons(db, site.brand_id, layout.id)}
        for layout in layouts
    ]
