"""Pydantic schemas for PrinterLocation requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PrinterLocationOut(BaseModel):
    """Serialised printer location for API responses."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    name: str
    copy_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrinterLocationCreate(BaseModel):
    """Payload for creating a new printer location — its docket template is auto-created with it."""

    name: str = Field(..., min_length=1, max_length=255)
    copy_count: int = Field(1, ge=1, description="Number of times the order docket prints for this location")


class PrinterLocationUpdate(BaseModel):
    """Payload for updating a printer location's mutable fields."""

    name: str | None = Field(None, min_length=1, max_length=255)
    copy_count: int | None = Field(None, ge=1)
    is_active: bool | None = None
