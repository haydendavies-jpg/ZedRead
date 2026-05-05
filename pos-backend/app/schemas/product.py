"""Pydantic schemas for product and site override requests and responses."""

import uuid

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """Payload for POST /products."""

    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    base_price_cents: int = Field(..., ge=0, description="Price in cents — never a float")
    display_order: int = Field(0, ge=0)


class ProductUpdate(BaseModel):
    """Payload for PATCH /products/{id} — all fields optional."""

    category_id: uuid.UUID | None = None
    tax_category_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    base_price_cents: int | None = Field(None, ge=0)
    display_order: int | None = Field(None, ge=0)


class ProductResponse(BaseModel):
    """Response schema for a Product."""

    id: uuid.UUID
    brand_id: uuid.UUID
    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None
    name: str
    description: str | None
    base_price_cents: int
    photo_url: str | None
    display_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class SiteProductOverrideSet(BaseModel):
    """Payload for PUT /site-overrides/{site_id}/{product_id}."""

    override_price_cents: int | None = Field(None, ge=0)
    is_excluded: bool = False


class SiteProductOverrideResponse(BaseModel):
    """Response schema for a SiteProductOverride."""

    id: uuid.UUID
    site_id: uuid.UUID
    product_id: uuid.UUID
    override_price_cents: int | None
    is_excluded: bool

    model_config = {"from_attributes": True}


class ResolvedProduct(BaseModel):
    """
    A product as seen by a specific site — price overrides and exclusions applied.

    Returned by resolve_products_for_site() and used directly by the invoice engine
    in Stage 10. Never modify this schema's fields without updating the invoice service.
    """

    product_id: uuid.UUID
    name: str
    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None
    effective_price_cents: int
    photo_url: str | None
    display_order: int
