"""Pydantic schemas for product requests and responses."""

import uuid

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """Payload for POST /products.

    base_price_cents is the tax-INCLUSIVE price. The tax-exclusive price is
    derived server-side from the brand's country tax rate; is_taxable decides
    which price is charged at sale.
    """

    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    print_name: str | None = Field(None, max_length=255, description="Docket name — falls back to name when unset")
    base_price_cents: int = Field(..., ge=0, description="Tax-inclusive price in cents — never a float")
    is_taxable: bool = Field(True, description="True → charge inclusive price with GST; False → charge exclusive price")
    is_open_item: bool = Field(False, description="True → sellable with a freely-entered name/price at sale time")
    display_order: int = Field(0, ge=0)


class ProductUpdate(BaseModel):
    """Payload for PATCH /products/{id} — all fields optional."""

    category_id: uuid.UUID | None = None
    tax_category_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    print_name: str | None = Field(None, max_length=255)
    base_price_cents: int | None = Field(None, ge=0, description="Tax-inclusive price in cents")
    is_taxable: bool | None = None
    is_open_item: bool | None = None
    display_order: int | None = Field(None, ge=0)


class ProductResponse(BaseModel):
    """Response schema for a Product."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None
    name: str
    description: str | None
    print_name: str | None
    effective_print_name: str
    base_price_cents: int
    price_ex_cents: int
    is_taxable: bool
    is_open_item: bool
    photo_url: str | None
    display_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ProductListItem(ProductResponse):
    """
    Response schema for GET /products — ProductResponse plus joined Category and
    Reporting Group names (Stage 20 table view). Not denormalized onto the
    Product row itself; resolved via a join in product_service.list_products().
    """

    category_name: str
    category_color: str
    reporting_group_id: uuid.UUID
    reporting_group_name: str
    modifier_names: str | None = None
