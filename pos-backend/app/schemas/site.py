"""Pydantic schemas for Site requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SiteCreate(BaseModel):
    """Payload for creating a new Site under a Brand."""

    brand_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)


class SiteUpdate(BaseModel):
    """Payload for updating a Site. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class SiteResponse(BaseModel):
    """Response shape returned for a Site."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
