"""Pydantic schemas for Menu requests and responses.

A Menu is a saved, schedulable configuration distinct from a MenuLayout (the
button arrangement) — see app/models/menu.py.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MenuOut(BaseModel):
    """Serialised menu for API responses."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    site_id: uuid.UUID | None
    scope: str
    menu_layout_id: uuid.UUID | None
    name: str
    note: str | None
    status: str
    scheduled_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MenuCreate(BaseModel):
    """Payload for creating a menu."""

    name: str = Field(..., min_length=1, max_length=255)
    note: str | None = Field(None, max_length=255)
    scope: str = Field("brand", pattern="^(brand|site)$")
    site_id: uuid.UUID | None = Field(None, description="Required when scope='site'")
    menu_layout_id: uuid.UUID | None = None


class MenuUpdate(BaseModel):
    """Payload for updating a menu's mutable fields — all optional."""

    name: str | None = Field(None, min_length=1, max_length=255)
    note: str | None = Field(None, max_length=255)
    scope: str | None = Field(None, pattern="^(brand|site)$")
    site_id: uuid.UUID | None = None
    menu_layout_id: uuid.UUID | None = None


class MenuSchedule(BaseModel):
    """Payload for scheduling a menu's publish."""

    scheduled_at: datetime
