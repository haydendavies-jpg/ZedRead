"""Pydantic schemas for Brand requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BrandCreate(BaseModel):
    """Payload for creating a new Brand under a Group."""

    group_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)


class BrandUpdate(BaseModel):
    """Payload for updating a Brand. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class BrandResponse(BaseModel):
    """Response shape returned for a Brand."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
