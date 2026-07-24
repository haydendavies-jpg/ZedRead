"""Pydantic schemas for product requests and responses."""

import uuid

from pydantic import BaseModel, Field, model_validator


class ProductCreate(BaseModel):
    """Payload for POST /products.

    base_price_cents is the tax-INCLUSIVE price. The tax-exclusive price is
    derived server-side from the brand's country tax rate; is_taxable decides
    which price is charged at sale.
    """

    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None = None
    printer_location_id: uuid.UUID | None = Field(None, description="Order-docket print station this product groups under")
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
    printer_location_id: uuid.UUID | None = Field(
        None,
        description=(
            "Order-docket print station this product groups under. Checked via "
            "model_fields_set (not `is not None`) so an explicit {'printer_location_id': "
            "null} clears it back to 'prints on no docket' — same idiom as "
            "menu_builder_service.update_menu_button's color."
        ),
    )
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    print_name: str | None = Field(None, max_length=255)
    base_price_cents: int | None = Field(None, ge=0, description="Tax-inclusive price in cents")
    is_taxable: bool | None = None
    is_open_item: bool | None = None
    display_order: int | None = Field(None, ge=0)
    is_sold_out: bool | None = Field(
        None, description="Set/clear from the Android Register's long-press product popup"
    )


class ProductResponse(BaseModel):
    """Response schema for a Product."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    category_id: uuid.UUID
    tax_category_id: uuid.UUID | None
    printer_location_id: uuid.UUID | None
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
    is_sold_out: bool

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
    printer_location_name: str | None = None


class ProductBulkUpdate(BaseModel):
    """
    Payload for POST /products/bulk — apply one or more field changes to a set
    of products in a single all-or-nothing transaction.

    Every field besides product_ids is optional; a single call may combine
    several (e.g. category_id + price_markup_percent together), applied to
    every product in product_ids.

    tax_category_id follows the model_fields_set idiom (see
    access_grant_service.update_grant's backend_role precedent) so an
    explicit {"tax_category_id": null} clears the product-level override back
    to inheriting from the category, distinct from omitting the field
    entirely (leave unchanged) — check payload.model_fields_set, not the
    field's value, to tell the two apart.

    is_active=False is the bulk archive action: besides flipping the flag it
    cascades — deleting every product_modifier_group_links row for the
    archived products, and every menu_buttons row (kind='product') across the
    brand's menu_layouts whose product_ref matches one of them. is_active=True
    only reactivates; no cascade runs in that direction.
    """

    product_ids: list[uuid.UUID] = Field(..., min_length=1)
    category_id: uuid.UUID | None = Field(None, description="Reassigns category (and thus effective reporting group)")
    price_cents: int | None = Field(None, ge=0, description="Overwrite base_price_cents for all selected — mutually exclusive with price_markup_percent")
    price_markup_percent: float | None = Field(
        None, description="Multiply each selected product's current base_price_cents by (1 + percent/100) — mutually exclusive with price_cents"
    )
    tax_category_id: uuid.UUID | None = Field(None, description="Reassign tax category; explicit null clears the override — see class docstring")
    modifier_group_id: uuid.UUID | None = Field(None, description="Attach this modifier group to selected products missing it — attach-only, never detaches")
    is_active: bool | None = Field(None, description="False is the bulk archive action (cascades); True only reactivates")

    @model_validator(mode="after")
    def _validate_price_fields_mutually_exclusive(self) -> "ProductBulkUpdate":
        """Reject a payload that sets both price_cents and price_markup_percent — they conflict."""
        if self.price_cents is not None and self.price_markup_percent is not None:
            raise ValueError("price_cents and price_markup_percent are mutually exclusive")
        return self


class ProductBulkUpdateResult(BaseModel):
    """Response for POST /products/bulk."""

    updated_count: int = Field(..., description="Number of products that had at least one field actually change")
    updated_product_ids: list[uuid.UUID] = Field(..., description="IDs of the products that were modified")
