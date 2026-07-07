"""Pydantic schemas for Reporting Group requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportingGroupOut(BaseModel):
    """Serialised reporting group for API responses."""

    id: uuid.UUID
    brand_id: uuid.UUID
    ref: str
    name: str
    is_default: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportingGroupCreate(BaseModel):
    """Payload for creating a new reporting group."""

    name: str


class ReportingGroupUpdate(BaseModel):
    """Payload for renaming a reporting group."""

    name: str | None = None
