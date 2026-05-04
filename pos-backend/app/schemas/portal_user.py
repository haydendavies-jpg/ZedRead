"""Pydantic schemas for PortalUser management requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class PortalUserCreate(BaseModel):
    """Payload for creating a new portal user (super_admin only)."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=12)
    role: str = Field(default="admin", pattern="^(super_admin|admin|reseller)$")


class PortalUserUpdate(BaseModel):
    """Payload for updating a portal user. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, pattern="^(super_admin|admin|reseller)$")


class PortalUserResponse(BaseModel):
    """Response shape returned for a PortalUser. Never includes password_hash."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
