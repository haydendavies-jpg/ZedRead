"""Pydantic schemas for tax category and tax rate requests and responses."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.constants.statuses import TaxModel


class TaxCategoryCreate(BaseModel):
    """Payload for POST /tax/categories."""

    name: str = Field(..., min_length=1, max_length=100)


class TaxCategoryUpdate(BaseModel):
    """Payload for PATCH /tax/categories/{id} — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)


class TaxCategoryResponse(BaseModel):
    """Response schema for a TaxCategory."""

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class TaxRateCreate(BaseModel):
    """Payload for POST /tax/categories/{tax_category_id}/rates."""

    name: str = Field(..., min_length=1, max_length=100)
    rate_percent: Decimal = Field(..., gt=Decimal("0"), le=Decimal("100"))
    tax_model: TaxModel


class TaxRateUpdate(BaseModel):
    """Payload for PATCH /tax/rates/{id} — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    rate_percent: Decimal | None = Field(None, gt=Decimal("0"), le=Decimal("100"))
    tax_model: TaxModel | None = None


class TaxRateResponse(BaseModel):
    """Response schema for a TaxRate."""

    id: uuid.UUID
    tax_category_id: uuid.UUID
    name: str
    rate_percent: Decimal
    tax_model: str
    is_active: bool

    model_config = {"from_attributes": True}
