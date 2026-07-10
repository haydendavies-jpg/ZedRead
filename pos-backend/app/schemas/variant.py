"""Pydantic schemas for product variant requests and responses."""

import uuid

from pydantic import BaseModel, Field


class AttributeAssignment(BaseModel):
    """One attribute type → value pair for a variant."""

    attribute_type_id: uuid.UUID
    attribute_value_id: uuid.UUID


class VariantCreate(BaseModel):
    """Payload for creating a product variant."""

    attributes: list[AttributeAssignment] = Field(..., min_length=1)
    sku: str | None = None
    price_cents: int | None = Field(None, ge=0)
    display_name: str | None = Field(
        None, max_length=255, description="Management-facing label distinct from the attribute-derived name"
    )


class VariantUpdate(BaseModel):
    """Payload for updating a variant — attributes are immutable after creation."""

    sku: str | None = None
    price_cents: int | None = Field(None, ge=0)
    display_name: str | None = Field(None, max_length=255)


class VariantResponse(BaseModel):
    """Response schema for a variant."""

    id: uuid.UUID
    ref: str
    product_id: uuid.UUID
    sku: str | None
    price_cents: int | None
    display_name: str | None
    is_active: bool
    attributes: list[AttributeAssignment]

    model_config = {"from_attributes": True}


class VariantListItem(VariantResponse):
    """
    Response schema for GET /variants — VariantResponse plus the joined parent
    product's name and ref (Stage 22), so the combined Variants+Combos portal
    page can show "linked product" without a second round-trip per row.
    """

    product_name: str
    product_ref: str
