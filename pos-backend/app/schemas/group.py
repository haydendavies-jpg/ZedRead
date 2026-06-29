"""Pydantic schemas for Group requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    """Payload for creating a new Group."""

    name: str = Field(..., min_length=1, max_length=255)


class GroupUpdate(BaseModel):
    """Payload for updating a Group. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class GroupResponse(BaseModel):
    """Response shape returned for a Group."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ref: str
    name: str
    is_active: bool
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
