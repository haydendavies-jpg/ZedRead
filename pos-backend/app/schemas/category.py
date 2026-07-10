"""Pydantic schemas for Category requests and responses."""

import uuid

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    """Payload for creating a new product category.

    reporting_group_id is optional on the wire — omitting it auto-assigns the
    brand's default reporting group (Stage 16: every category must have one).
    """

    name: str
    brand_id: uuid.UUID
    reporting_group_id: uuid.UUID | None = None
    display_order: int = 0


class CategoryUpdate(BaseModel):
    """Payload for updating a category's mutable fields."""

    name: str | None = None
    reporting_group_id: uuid.UUID | None = None
    display_order: int | None = None
    is_active: bool | None = None
