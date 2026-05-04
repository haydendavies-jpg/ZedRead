"""Pydantic request/response schemas for the /licenses routes."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LicenseCreate(BaseModel):
    """Payload for POST /licenses — create a new license for a site."""

    site_id: uuid.UUID
    plan_name: str = Field(..., min_length=1, max_length=100)
    monthly_fee_cents: int = Field(..., ge=0, description="Monthly fee in cents; 0 for free plans")
    is_trial: bool = False
    starts_at: datetime
    expires_at: datetime


class LicenseUpdate(BaseModel):
    """Payload for PATCH /licenses/{id} — update mutable license fields."""

    plan_name: str | None = Field(default=None, min_length=1, max_length=100)
    monthly_fee_cents: int | None = Field(default=None, ge=0)
    expires_at: datetime | None = None


class LicenseResponse(BaseModel):
    """Serialised License returned by all /licenses routes."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    site_id: uuid.UUID
    plan_name: str
    status: str
    monthly_fee_cents: int
    is_trial: bool
    starts_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
