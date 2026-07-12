"""Business logic for the POS Menu Builder (Stage 23).

A MenuLayout is a named, graphical POS menu: an ordered set of MenuTab rows,
each holding an ordered set of MenuButton rows. Buttons reference products by
their human-readable `ref` code rather than a foreign key, so a button
survives the underlying product being deleted and recreated with the same
code (see app/models/menu_button.py). Publishing a layout is a warn-don't-block
operation: a button whose code no longer resolves to an active product is
reported back to the caller but does not stop the publish.

Prototype scope: single-level tabs + buttons only, no nested sub-menus.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    MENU_BUTTON_ADDED,
    MENU_BUTTON_REMOVED,
    MENU_BUTTON_REORDERED,
    MENU_LAYOUT_CREATED,
    MENU_LAYOUT_DELETED,
    MENU_LAYOUT_PUBLISHED,
    MENU_LAYOUT_UNPUBLISHED,
    MENU_LAYOUT_UPDATED,
    MENU_TAB_CREATED,
    MENU_TAB_DELETED,
    MENU_TAB_REORDERED,
    MENU_TAB_UPDATED,
)
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
    """
    Fetch a MenuLayout by id scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: The brand the layout must belong to.
        layout_id: UUID of the layout to fetch.

    Returns:
        MenuLayout: The found layout.

    Raises:
        HTTPException: 404 if no layout with this id exists for this brand.
    """
    result = await db.execute(
        select(MenuLayout).where(MenuLayout.id == layout_id, MenuLayout.brand_id == brand_id)
    )
    layout = result.scalar_one_or_none()
    if layout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu layout not found")
    return layout


async def _get_tab_or_404(db: AsyncSession, layout_id: uuid.UUID, tab_id: uuid.UUID) -> MenuTab:
    """
    Fetch a MenuTab by id scoped to a layout, or raise HTTP 404.

    Args:
        db: Active database session.
        layout_id: The layout the tab must belong to.
        tab_id: UUID of the tab to fetch.

    Returns:
        MenuTab: The found tab.

    Raises:
        HTTPException: 404 if no tab with this id exists for this layout.
    """
    result = await db.execute(select(MenuTab).where(MenuTab.id == tab_id, MenuTab.layout_id == layout_id))
    tab = result.scalar_one_or_none()
    if tab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu tab not found")
    return tab


async def _get_button_or_404(db: AsyncSession, tab_id: uuid.UUID, button_id: uuid.UUID) -> MenuButton:
    """
    Fetch a MenuButton by id scoped to a tab, or raise HTTP 404.

    Args:
        db: Active database session.
        tab_id: The tab the button must belong to.
        button_id: UUID of the button to fetch.

    Returns:
        MenuButton: The found button.

    Raises:
        HTTPException: 404 if no button with this id exists for this tab.
    """
    result = await db.execute(
        select(MenuButton).where(MenuButton.id == button_id, MenuButton.tab_id == tab_id)
    )
    button = result.scalar_one_or_none()
    if button is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu button not found")
    return button


async def _resolve_products_by_ref(
    db: AsyncSession, brand_id: uuid.UUID, refs: set[str]
) -> dict[str, Product]:
    """
    Look up a set of product ref codes within a brand in a single query.

    Args:
        db: Active database session.
        brand_id: The brand to scope the lookup to.
        refs: The set of product ref codes to resolve.

    Returns:
        dict[str, Product]: Maps each resolved ref to its Product row. Refs
            with no matching product in this brand are simply absent.
    """
    if not refs:
        return {}
    result = await db.execute(
        select(Product).where(Product.brand_id == brand_id, Product.ref.in_(refs))
    )
    return {p.ref: p for p in result.scalars().all()}


async def _load_buttons_for_tabs(db: AsyncSession, tab_ids: list[uuid.UUID]) -> list[MenuButton]:
    """
    Load every button belonging to any of the given tabs, ordered by display_order.

    Args:
        db: Active database session.
        tab_ids: The tab ids to load buttons for.

    Returns:
        list[MenuButton]: Empty list if tab_ids is empty (avoids an unnecessary query).
    """
    if not tab_ids:
        return []
    result = await db.execute(
        select(MenuButton).where(MenuButton.tab_id.in_(tab_ids)).order_by(MenuButton.display_order)
    )
    return list(result.scalars().all())


def _build_button_out(button: MenuButton, product: Product | None) -> MenuButtonOut:
    """
    Combine a stored MenuButton row with its (possibly missing) resolved product.

    Args:
        button: The stored button row.
        product: The resolved Product, or None if the ref no longer resolves.

    Returns:
        MenuButtonOut: The button with a live product preview attached.
    """
    return MenuButtonOut(
        id=button.id,
        tab_id=button.tab_id,
        product_ref=button.product_ref,
        display_order=button.display_order,
        product_name=product.name if product else None,
        price_cents=product.base_price_cents if product else None,
        is_active=product.is_active if product else None,
    )


async def _load_tabs_with_buttons(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID
) -> list[MenuTabOut]:
    """
    Load every tab in a layout with its ordered, resolved buttons.

    Args:
        db: Active database session.
        brand_id: The brand the layout's products must resolve against.
        layout_id: The layout to load tabs for.

    Returns:
        list[MenuTabOut]: Tabs ordered by display_order, each with buttons
            ordered by display_order and resolved against the brand's catalog.
    """
    tabs_result = await db.execute(
        select(MenuTab).where(MenuTab.layout_id == layout_id).order_by(MenuTab.display_order)
    )
    tabs = list(tabs_result.scalars().all())

    buttons = await _load_buttons_for_tabs(db, [t.id for t in tabs])
    products_by_ref = await _resolve_products_by_ref(db, brand_id, {b.product_ref for b in buttons})

    buttons_by_tab: dict[uuid.UUID, list[MenuButton]] = {}
    for b in buttons:
        buttons_by_tab.setdefault(b.tab_id, []).append(b)

    return [
        MenuTabOut(
            id=t.id,
            layout_id=t.layout_id,
            name=t.name,
            display_order=t.display_order,
            buttons=[_build_button_out(b, products_by_ref.get(b.product_ref)) for b in buttons_by_tab.get(t.id, [])],
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
) -> list[MenuLayout]:
    """
    List menu layouts for a brand, optionally filtered to one site's scope.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to list layouts for.
        site_id: If given, only include brand-wide layouts and layouts scoped to this site.
        skip: Pagination offset.
        limit: Maximum number of layouts to return.

    Returns:
        list[MenuLayout]: Layouts ordered by name.
    """
    query = select(MenuLayout).where(MenuLayout.brand_id == brand_id)
    if site_id is not None:
        query = query.where((MenuLayout.scope == "brand") | (MenuLayout.site_id == site_id))
    query = query.order_by(MenuLayout.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_menu_layout_detail(db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID) -> dict:
    """
    Fetch a menu layout with its tabs and resolved buttons.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to fetch.

    Returns:
        dict: Keys 'layout' (MenuLayout) and 'tabs' (list[MenuTabOut]).

    Raises:
        HTTPException: 404 if not found.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)
    tabs = await _load_tabs_with_buttons(db, brand_id, layout_id)
    return {"layout": layout, "tabs": tabs}


async def create_menu_layout(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: MenuLayoutCreate,
    actor: User | SuperAdmin,
) -> MenuLayout:
    """
    Create a new menu layout.

    Args:
        db: Active database session.
        brand_id: UUID of the brand to create the layout under.
        payload: Layout creation data.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuLayout: The created layout.

    Raises:
        HTTPException: 400 if scope='site' with a site_id from another brand.
    """
    if payload.scope == "site":
        if payload.site_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id is required when scope='site'")
        site_result = await db.execute(select(Site).where(Site.id == payload.site_id, Site.brand_id == brand_id))
        if site_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id does not belong to this brand")

    layout = MenuLayout(
        id=uuid.uuid4(),
        brand_id=brand_id,
        site_id=payload.site_id if payload.scope == "site" else None,
        scope=payload.scope,
        name=payload.name,
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
    Rename a menu layout.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to update.
        payload: Fields to update.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuLayout: The updated layout.

    Raises:
        HTTPException: 404 if not found.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)

    before: dict = {}
    if payload.name is not None:
        before["name"] = layout.name
        layout.name = payload.name

    await log_action(
        db=db,
        action=MENU_LAYOUT_UPDATED,
        entity_type="menu_layout",
        entity_id=str(layout.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(layout)
    return layout


async def delete_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> None:
    """
    Delete a menu layout and its tabs/buttons (cascade).

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to delete.
        actor: The authenticated user performing the action (for audit logging).

    Raises:
        HTTPException: 404 if not found.
    """
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


async def publish_menu_layout(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, actor: User | SuperAdmin
) -> tuple[MenuLayout, list[PublishWarning]]:
    """
    Publish a menu layout, bumping its version. Does not block on stale button refs.

    A button whose product_ref no longer resolves to an active product in the
    brand is reported as a warning rather than failing the publish — per the
    stage plan's "warn (don't silently fail)" requirement.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to publish.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        tuple[MenuLayout, list[PublishWarning]]: The published layout and any warnings.

    Raises:
        HTTPException: 404 if not found.
    """
    layout = await _get_layout_or_404(db, brand_id, layout_id)

    tabs_result = await db.execute(select(MenuTab).where(MenuTab.layout_id == layout_id))
    tabs = {t.id: t for t in tabs_result.scalars().all()}
    buttons = await _load_buttons_for_tabs(db, list(tabs.keys()))
    products_by_ref = await _resolve_products_by_ref(db, brand_id, {b.product_ref for b in buttons})

    warnings: list[PublishWarning] = []
    for button in buttons:
        product = products_by_ref.get(button.product_ref)
        if product is None:
            warnings.append(
                PublishWarning(
                    button_id=button.id,
                    tab_name=tabs[button.tab_id].name,
                    product_ref=button.product_ref,
                    reason=_PRODUCT_NOT_FOUND,
                )
            )
        elif not product.is_active:
            warnings.append(
                PublishWarning(
                    button_id=button.id,
                    tab_name=tabs[button.tab_id].name,
                    product_ref=button.product_ref,
                    reason=_PRODUCT_INACTIVE,
                )
            )

    layout.is_published = True
    layout.version += 1

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
    """
    Unpublish a menu layout.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to unpublish.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuLayout: The unpublished layout.

    Raises:
        HTTPException: 404 if not found.
    """
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


# ── Tab CRUD ──────────────────────────────────────────────────────────────────


async def create_menu_tab(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    payload: MenuTabCreate,
    actor: User | SuperAdmin,
) -> MenuTab:
    """
    Add a tab to a menu layout, appended after any existing tabs.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout to add the tab to.
        payload: Tab creation data.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuTab: The created tab.

    Raises:
        HTTPException: 404 if the layout does not exist for this brand.
    """
    await _get_layout_or_404(db, brand_id, layout_id)

    max_order_result = await db.execute(
        select(MenuTab.display_order).where(MenuTab.layout_id == layout_id).order_by(MenuTab.display_order.desc())
    )
    max_order = max_order_result.scalars().first()

    tab = MenuTab(
        id=uuid.uuid4(),
        layout_id=layout_id,
        name=payload.name,
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
        after_state={"name": tab.name, "layout_id": str(layout_id)},
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
    """
    Rename a menu tab.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout the tab belongs to.
        tab_id: UUID of the tab to update.
        payload: Fields to update.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuTab: The updated tab.

    Raises:
        HTTPException: 404 if not found.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    tab = await _get_tab_or_404(db, layout_id, tab_id)

    before: dict = {}
    if payload.name is not None:
        before["name"] = tab.name
        tab.name = payload.name

    await log_action(
        db=db,
        action=MENU_TAB_UPDATED,
        entity_type="menu_tab",
        entity_id=str(tab.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(tab)
    return tab


async def delete_menu_tab(
    db: AsyncSession, brand_id: uuid.UUID, layout_id: uuid.UUID, tab_id: uuid.UUID, actor: User | SuperAdmin
) -> None:
    """
    Delete a menu tab and its buttons (cascade).

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout the tab belongs to.
        tab_id: UUID of the tab to delete.
        actor: The authenticated user performing the action (for audit logging).

    Raises:
        HTTPException: 404 if not found.
    """
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
    Reorder a layout's tabs — each id in tab_ids gets display_order = its list index.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout whose tabs are being reordered.
        tab_ids: The full, ordered list of tab ids for this layout.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        list[MenuTab]: The reordered tabs.

    Raises:
        HTTPException: 404 if the layout or any tab_id does not belong to it.
    """
    await _get_layout_or_404(db, brand_id, layout_id)

    existing_result = await db.execute(select(MenuTab).where(MenuTab.layout_id == layout_id))
    existing_by_id = {t.id: t for t in existing_result.scalars().all()}

    if set(tab_ids) != set(existing_by_id.keys()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tab_ids must include exactly the layout's current tabs",
        )

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
    Add a button to a tab, referencing a product by its ref code.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout the tab belongs to.
        tab_id: UUID of the tab to add the button to.
        payload: Button creation data (the product ref code).
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuButtonOut: The created button with its resolved product preview.

    Raises:
        HTTPException: 404 if the layout or tab does not exist.
        HTTPException: 400 if product_ref does not resolve to an active product in this brand.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)

    product_result = await db.execute(
        select(Product).where(Product.brand_id == brand_id, Product.ref == payload.product_ref)
    )
    product = product_result.scalar_one_or_none()
    if product is None or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_ref does not resolve to an active product in this brand",
        )

    max_order_result = await db.execute(
        select(MenuButton.display_order).where(MenuButton.tab_id == tab_id).order_by(MenuButton.display_order.desc())
    )
    max_order = max_order_result.scalars().first()

    button = MenuButton(
        id=uuid.uuid4(),
        tab_id=tab_id,
        product_ref=payload.product_ref,
        display_order=(max_order + 1) if max_order is not None else 0,
    )
    db.add(button)
    await db.flush()

    await log_action(
        db=db,
        action=MENU_BUTTON_ADDED,
        entity_type="menu_button",
        entity_id=str(button.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"product_ref": button.product_ref, "tab_id": str(tab_id)},
    )
    await db.commit()
    await db.refresh(button)
    return _build_button_out(button, product)


async def delete_menu_button(
    db: AsyncSession,
    brand_id: uuid.UUID,
    layout_id: uuid.UUID,
    tab_id: uuid.UUID,
    button_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> None:
    """
    Remove a button from a tab.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout the tab belongs to.
        tab_id: UUID of the tab the button belongs to.
        button_id: UUID of the button to remove.
        actor: The authenticated user performing the action (for audit logging).

    Raises:
        HTTPException: 404 if not found.
    """
    await _get_layout_or_404(db, brand_id, layout_id)
    await _get_tab_or_404(db, layout_id, tab_id)
    button = await _get_button_or_404(db, tab_id, button_id)

    await log_action(
        db=db,
        action=MENU_BUTTON_REMOVED,
        entity_type="menu_button",
        entity_id=str(button.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"product_ref": button.product_ref, "tab_id": str(tab_id)},
    )
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
    Reorder a tab's buttons, and/or move buttons into this tab from another.

    Every id in button_ids is (re)assigned to this tab_id and given
    display_order = its index in the list. A button moved from another tab
    in the same layout is implicitly removed from its old tab by this
    reassignment — the frontend only needs to call this once, against the
    destination tab, after a drag-and-drop move.

    Args:
        db: Active database session.
        brand_id: UUID of the brand the layout belongs to.
        layout_id: UUID of the layout the tab belongs to.
        tab_id: UUID of the destination tab.
        button_ids: The full, ordered list of button ids that should end up in this tab.
        actor: The authenticated user performing the action (for audit logging).

    Returns:
        MenuTabOut: The destination tab with its reordered, resolved buttons.

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
        db=db,
        action=MENU_BUTTON_REORDERED,
        entity_type="menu_tab",
        entity_id=str(tab_id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"reordered_button_ids": [str(i) for i in button_ids]},
    )
    await db.commit()

    tabs = await _load_tabs_with_buttons(db, brand_id, layout_id)
    return next(t for t in tabs if t.id == tab_id)


# ── POS consumption contract ──────────────────────────────────────────────────


async def get_published_menu_layouts_for_site(db: AsyncSession, site: Site) -> list[dict]:
    """
    Fetch every published menu layout visible to a site (brand-wide + site-specific).

    This is the read-only contract Android will eventually consume via
    GET /pos/menu-layout?site_id=. Android-side consumption is out of scope
    for this stage — only the contract is built.

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
    layouts = list(result.scalars().all())
    return [
        {"layout": layout, "tabs": await _load_tabs_with_buttons(db, site.brand_id, layout.id)}
        for layout in layouts
    ]
