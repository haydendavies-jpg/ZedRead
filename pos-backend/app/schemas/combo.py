"""Pydantic schemas for combo group and combo option requests and responses."""

import uuid

from pydantic import BaseModel, Field


class ComboGroupCreate(BaseModel):
    """Payload for creating a combo group."""

    name: str = Field(..., min_length=1, max_length=100)
    display_name: str | None = Field(
        None, max_length=255, description="Management-facing label distinct from the POS-facing name"
    )
    min_selections: int = Field(1, ge=0)
    max_selections: int = Field(1, ge=1)
    is_required: bool = True
    display_order: int = Field(0, ge=0)


class ComboGroupUpdate(BaseModel):
    """Payload for updating a combo group's mutable fields — all optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    min_selections: int | None = Field(None, ge=0)
    max_selections: int | None = Field(None, ge=1)
    is_required: bool | None = None
    display_order: int | None = Field(None, ge=0)


class ComboGroupResponse(BaseModel):
    """Response schema for a combo group."""

    id: uuid.UUID
    ref: str
    product_id: uuid.UUID
    name: str
    display_name: str | None
    min_selections: int
    max_selections: int
    is_required: bool
    display_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ComboGroupListItem(ComboGroupResponse):
    """
    Response schema for GET /combos — ComboGroupResponse plus the joined parent
    product's name and ref (Stage 22), so the combined Variants+Combos portal
    page can show "linked product" without a second round-trip per row.
    """

    product_name: str
    product_ref: str


class ComboOptionCreate(BaseModel):
    """Payload for adding an option to a combo group."""

    product_id: uuid.UUID
    price_delta_cents: int = Field(0)
    display_order: int = Field(0, ge=0)


class ComboOptionResponse(BaseModel):
    """Response schema for a combo option."""

    id: uuid.UUID
    combo_group_id: uuid.UUID
    product_id: uuid.UUID
    price_delta_cents: int
    display_order: int

    model_config = {"from_attributes": True}
