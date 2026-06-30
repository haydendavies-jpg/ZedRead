"""Pydantic schemas for Brand requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BrandCreate(BaseModel):
    """Payload for creating a new Brand under a Group.

    timezone/currency/country default to Australia/Sydney, AUD, AU (same
    defaults as migration 0028's backfill) so they can be omitted, but
    every Brand create form in the portal should always supply them
    explicitly — both fields are required independently per level, with no
    inheritance from the parent Group.
    """

    group_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    timezone: str = Field(default="Australia/Sydney", min_length=1, max_length=64)
    currency: str = Field(default="AUD", min_length=3, max_length=3)
    country: str = Field(default="AU", min_length=2, max_length=2)
    tax_id_value: str | None = Field(default=None, max_length=50)
    billing_email: str | None = Field(default=None, max_length=255)


class BrandUpdate(BaseModel):
    """Payload for updating a Brand. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    tax_id_value: str | None = Field(default=None, max_length=50)
    billing_email: str | None = Field(default=None, max_length=255)


class BrandResponse(BaseModel):
    """Response shape returned for a Brand."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ref: str
    group_id: uuid.UUID
    name: str
    is_active: bool
    timezone: str
    currency: str
    country: str
    tax_id_value: str | None
    logo_url: str | None
    billing_email: str | None
    created_at: datetime
    updated_at: datetime
