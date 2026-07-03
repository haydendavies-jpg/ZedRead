"""Pydantic schemas for admin-managed tax template requests and responses."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.constants.statuses import TaxModel


class TaxTemplateRateCreate(BaseModel):
    """Payload for POST /admin/tax-templates/{template_id}/rates."""

    name: str = Field(..., min_length=1, max_length=100)
    rate_percent: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))
    tax_model: TaxModel
    display_order: int = Field(default=0, ge=0)


class TaxTemplateRateUpdate(BaseModel):
    """Payload for PATCH /admin/tax-templates/rates/{rate_id} — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    rate_percent: Decimal | None = Field(None, ge=Decimal("0"), le=Decimal("100"))
    tax_model: TaxModel | None = None
    display_order: int | None = Field(None, ge=0)


class TaxTemplateRateResponse(BaseModel):
    """Response schema for a TaxTemplateRate."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    tax_template_id: uuid.UUID
    name: str
    rate_percent: Decimal
    tax_model: str
    display_order: int
    is_active: bool


class TaxTemplateCreate(BaseModel):
    """Payload for POST /admin/tax-templates.

    country is required; state/county/city are optional and narrow the
    jurisdiction — unset fields mean the template applies at the wider level.
    """

    name: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=2, max_length=2)
    state: str | None = Field(None, max_length=100)
    county: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)


class TaxTemplateUpdate(BaseModel):
    """Payload for PATCH /admin/tax-templates/{template_id} — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=100)
    country: str | None = Field(None, min_length=2, max_length=2)
    state: str | None = Field(None, max_length=100)
    county: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    is_active: bool | None = None


class TaxTemplateResponse(BaseModel):
    """Response schema for a TaxTemplate, including its rates."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    country: str
    state: str | None
    county: str | None
    city: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    rates: list[TaxTemplateRateResponse] = Field(default_factory=list)
