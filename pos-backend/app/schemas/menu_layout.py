"""Pydantic schemas for POS Menu Builder requests and responses (Stage 23; Phase 2 grid editor)."""

import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class MenuButtonOut(BaseModel):
    """
    A resolved menu button — the stored row plus a live preview.

    For kind='product': product_name/price_cents/is_active/is_sold_out/
    category_color/product_photo_url are resolved live against the brand's
    catalog by product_ref (None when the ref no longer resolves —
    category_color powers the inspector's "Category default" colour reset
    and the tile's fallback fill when color is unset; product_photo_url
    renders as the tile's background image when the linked product has one).
    is_sold_out greys the POS tile out and blocks adding it to an order —
    set/cleared from the Register's own long-press product popup, not from
    Menu Studio.
    For kind='folder': child_tab_name/child_tab_button_count preview the
    nested tab this button opens.

    grid_col/grid_row are the button's explicit grid cell placement (drag-to-
    any-cell); both are None until the button has been moved via
    PATCH .../buttons/{button_id}/place, meaning the frontend should fall
    back to dense-pack layout from width/height/display_order.
    """

    id: uuid.UUID
    tab_id: uuid.UUID
    kind: str
    product_ref: str | None
    child_tab_id: uuid.UUID | None
    width: int
    height: int
    color: str | None
    display_order: int
    grid_col: int | None = None
    grid_row: int | None = None
    product_name: str | None = None
    price_cents: int | None = None
    is_active: bool | None = None
    is_sold_out: bool | None = None
    category_color: str | None = None
    product_photo_url: str | None = None
    child_tab_name: str | None = None
    child_tab_button_count: int | None = None


class MenuButtonCreate(BaseModel):
    """Payload for adding a button to a tab. kind='folder' creates a new nested MenuTab too."""

    kind: str = Field("product", pattern="^(product|folder)$")
    product_ref: str | None = Field(None, min_length=1, max_length=20, description="Required when kind='product'")
    name: str | None = Field(None, min_length=1, max_length=255, description="Nested tab name, required when kind='folder'")
    width: int = Field(1, ge=1, le=6)
    height: int = Field(1, ge=1, le=4)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)


class MenuButtonUpdate(BaseModel):
    """Payload for updating a button's mutable fields — all optional."""

    product_ref: str | None = Field(None, min_length=1, max_length=20)
    width: int | None = Field(None, ge=1, le=6)
    height: int | None = Field(None, ge=1, le=4)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)


class MenuButtonPlace(BaseModel):
    """
    Payload for PATCH /menu-layouts/buttons/{button_id}/place — drag a button to an explicit grid cell.

    tab_id is the destination tab (may be the button's current tab, or a
    different one in the same layout — a cross-tab drag). grid_col/grid_row
    address the button's new top-left cell; the service additionally checks
    grid_col + the button's stored width does not exceed the 6-column grid.
    No overlap checking is performed against other buttons in the same cell —
    dense-pack/CSS visually resolves minor overlaps and strict rejection would
    make quick drag-reorders error-prone.
    """

    tab_id: uuid.UUID
    grid_col: int = Field(..., ge=0, le=5)
    grid_row: int = Field(..., ge=0)


class MenuButtonsReorder(BaseModel):
    """
    Payload to reorder (and/or move into) a tab's buttons.

    Every listed button_id is (re)assigned to the target tab in the path and
    given display_order = its index in this list. A button moved from
    another tab is implicitly removed from its old tab by this reassignment
    — no separate call against the source tab is needed.
    """

    button_ids: list[uuid.UUID] = Field(..., min_length=0)


class MenuButtonsBulkColor(BaseModel):
    """Payload to bulk-recolor a multi-selection of buttons."""

    button_ids: list[uuid.UUID] = Field(..., min_length=1)
    color: str = Field(..., pattern=_HEX_COLOR_PATTERN)


class MenuButtonsBulkDelete(BaseModel):
    """Payload to bulk-delete a multi-selection of buttons."""

    button_ids: list[uuid.UUID] = Field(..., min_length=1)


class MenuButtonsBulkDeleteResult(BaseModel):
    """
    Response for POST /{layout_id}/buttons/bulk-delete.

    Lets the frontend patch its local cache (drop these ids) instead of
    refetching the whole layout. deleted_tab_ids covers folder buttons among
    the selection whose nested child tab cascade-deleted too — those ids also
    need dropping from any locally-cached tab tree.
    """

    deleted_button_ids: list[uuid.UUID]
    deleted_tab_ids: list[uuid.UUID]


class MenuButtonsGroupIntoTab(BaseModel):
    """Payload for the multi-select 'Group into tab' action — must all share one source tab."""

    button_ids: list[uuid.UUID] = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=255)


class MenuTabOut(BaseModel):
    """A tab plus its ordered, resolved buttons."""

    id: uuid.UUID
    layout_id: uuid.UUID
    parent_tab_id: uuid.UUID | None
    name: str
    color: str | None
    display_order: int
    buttons: list[MenuButtonOut]

    model_config = {"from_attributes": True}


class MenuTabCreate(BaseModel):
    """Payload for adding a tab to a layout. parent_tab_id nests it under a folder; omit for a top-level (rail) tab."""

    name: str = Field(..., min_length=1, max_length=255)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)
    parent_tab_id: uuid.UUID | None = None


class MenuTabUpdate(BaseModel):
    """Payload for updating a tab's mutable fields — all optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)


class MenuTabsReorder(BaseModel):
    """Payload to reorder a set of sibling tabs — every id gets display_order = its list index."""

    tab_ids: list[uuid.UUID] = Field(..., min_length=0)


class MenuLayoutOut(BaseModel):
    """Serialised menu layout for list views (no nested tabs/buttons)."""

    id: uuid.UUID
    brand_id: uuid.UUID
    site_id: uuid.UUID | None
    scope: str
    name: str
    color: str
    is_published: bool
    published_at: datetime | None
    version: int
    is_all_day: bool
    start_time: time | None
    end_time: time | None
    active_days: list[int]
    scheduled_publish_at: datetime | None
    is_default: bool
    button_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MenuLayoutDetail(MenuLayoutOut):
    """Full menu layout detail — every tab (flat, arbitrarily nested via parent_tab_id), each with ordered resolved buttons."""

    tabs: list[MenuTabOut]


class PosMenuLayoutDetail(MenuLayoutDetail):
    """
    GET /pos/menu-layout's per-layout response shape.

    is_effective_default is computed per-request (not the stored is_default
    column directly): among the currently-active published layouts returned
    for a site, at most one has is_effective_default=True — a site's own
    is_default site-scope layout takes precedence over the brand-wide
    is_default fallback. Lets Android distinguish the schedule-active
    default from a layout the staff manually switched to.
    """

    is_effective_default: bool = False


class MenuLayoutCreate(BaseModel):
    """Payload for creating a menu layout."""

    name: str = Field(..., min_length=1, max_length=255)
    scope: str = Field(..., pattern="^(brand|site)$")
    site_id: uuid.UUID | None = Field(None, description="Required when scope='site'")
    color: str = Field("#A82040", pattern=_HEX_COLOR_PATTERN)


class MenuLayoutUpdate(BaseModel):
    """Payload for updating a menu layout's mutable fields, including active-time scheduling — all optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)
    is_all_day: bool | None = None
    start_time: time | None = None
    end_time: time | None = None
    active_days: list[int] | None = Field(None, description="0=Monday .. 6=Sunday")
    is_default: bool | None = Field(
        None,
        description="Set True to make this the scheduled/default layout for its scope, clearing any other default in the same scope",
    )


class MenuLayoutSchedulePublish(BaseModel):
    """Payload for the 'Schedule publish' bulk action — persisted only, see MenuLayout docstring."""

    scheduled_publish_at: datetime


class PublishWarning(BaseModel):
    """One button whose product_ref did not resolve to an active product at publish time."""

    button_id: uuid.UUID
    tab_name: str
    product_ref: str
    reason: str


class PublishResult(BaseModel):
    """Response for POST /menu-layouts/{id}/publish — the layout plus any warnings."""

    layout: MenuLayoutOut
    warnings: list[PublishWarning]
