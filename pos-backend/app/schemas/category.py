"""Pydantic schemas for Category requests and responses."""

import uuid

from pydantic import BaseModel, Field

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class CategoryOut(BaseModel):
    """Serialised category for API responses."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    reporting_group_id: uuid.UUID
    name: str
    is_system: bool
    is_active: bool
    display_order: int
    default_color: str

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    """Payload for creating a new product category.

    reporting_group_id is optional on the wire — omitting it auto-assigns the
    brand's default reporting group (Stage 16: every category must have one).
    default_color defaults to the design system's neutral swatch when omitted.
    """

    name: str
    brand_id: uuid.UUID
    reporting_group_id: uuid.UUID | None = None
    display_order: int = 0
    default_color: str = Field("#5A5550", pattern=_HEX_COLOR_PATTERN)


class CategoryUpdate(BaseModel):
    """Payload for updating a category's mutable fields."""

    name: str | None = None
    reporting_group_id: uuid.UUID | None = None
    display_order: int | None = None
    is_active: bool | None = None
    default_color: str | None = Field(None, pattern=_HEX_COLOR_PATTERN)
