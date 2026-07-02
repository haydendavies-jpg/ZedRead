"""Pydantic schemas for Group requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class GroupCreate(BaseModel):
    """Payload for creating a new Group.

    timezone/currency/country default to Australia/Sydney, AUD, AU (the same
    defaults migration 0028 backfilled onto existing rows) so they can be
    omitted, but every Group create form in the portal should always supply
    them explicitly — both fields are required independently per level.
    """

    name: str = Field(..., min_length=1, max_length=255)
    timezone: str = Field(default="Australia/Sydney", min_length=1, max_length=64)
    currency: str = Field(default="AUD", min_length=3, max_length=3)
    country: str = Field(default="AU", min_length=2, max_length=2)
    tax_id_value: str | None = Field(default=None, max_length=50)
    billing_email: str | None = Field(default=None, max_length=255)
    master_email: EmailStr = Field(..., description="Login email for the auto-created Group master user")
    master_password: str = Field(..., min_length=8, description="Password for the auto-created Group master user")


class GroupUpdate(BaseModel):
    """Payload for updating a Group. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    tax_id_value: str | None = Field(default=None, max_length=50)
    billing_email: str | None = Field(default=None, max_length=255)


class GroupResponse(BaseModel):
    """Response shape returned for a Group."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ref: str
    name: str
    is_active: bool
    timezone: str
    currency: str
    country: str
    tax_id_value: str | None
    logo_url: str | None
    billing_email: str | None
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
