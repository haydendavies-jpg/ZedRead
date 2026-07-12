"""Pydantic schemas for POS Menu Builder requests and responses (Stage 23)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MenuButtonOut(BaseModel):
    """
    A resolved menu button — the stored row plus a live preview of the
    product it currently points to (name/price/active), resolved at read
    time by menu_builder_service.py. product_name/price_cents/is_active are
    None when product_ref no longer resolves to a product in the brand.
    """

    id: uuid.UUID
    tab_id: uuid.UUID
    product_ref: str
    display_order: int
    product_name: str | None
    price_cents: int | None
    is_active: bool | None


class MenuButtonCreate(BaseModel):
    """Payload for adding a button to a tab."""

    product_ref: str = Field(..., min_length=1, max_length=20)


class MenuButtonsReorder(BaseModel):
    """
    Payload to reorder (and/or move into) a tab's buttons.

    Every listed button_id is (re)assigned to the target tab in the path and
    given display_order = its index in this list. A button moved from
    another tab is implicitly removed from its old tab by this reassignment
    — no separate call against the source tab is needed.
    """

    button_ids: list[uuid.UUID] = Field(..., min_length=0)


class MenuTabOut(BaseModel):
    """A tab plus its ordered, resolved buttons."""

    id: uuid.UUID
    layout_id: uuid.UUID
    name: str
    display_order: int
    buttons: list[MenuButtonOut]

    model_config = {"from_attributes": True}


class MenuTabCreate(BaseModel):
    """Payload for adding a tab to a layout."""

    name: str = Field(..., min_length=1, max_length=255)


class MenuTabUpdate(BaseModel):
    """Payload for renaming a tab — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=255)


class MenuTabsReorder(BaseModel):
    """Payload to reorder a layout's tabs — every id gets display_order = its list index."""

    tab_ids: list[uuid.UUID] = Field(..., min_length=0)


class MenuLayoutOut(BaseModel):
    """Serialised menu layout for list views (no nested tabs/buttons)."""

    id: uuid.UUID
    brand_id: uuid.UUID
    site_id: uuid.UUID | None
    scope: str
    name: str
    is_published: bool
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MenuLayoutDetail(MenuLayoutOut):
    """Full menu layout detail — ordered tabs, each with ordered resolved buttons."""

    tabs: list[MenuTabOut]


class MenuLayoutCreate(BaseModel):
    """Payload for creating a menu layout."""

    name: str = Field(..., min_length=1, max_length=255)
    scope: str = Field(..., pattern="^(brand|site)$")
    site_id: uuid.UUID | None = Field(None, description="Required when scope='site'")


class MenuLayoutUpdate(BaseModel):
    """Payload for renaming a menu layout — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=255)


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
