"""Pydantic schemas for SuperAdmin management requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SuperAdminCreate(BaseModel):
    """Payload for creating a new portal user (super_admin only)."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=12)
    role: str = Field(default="admin", pattern="^(admin|reseller_staff)$")


class SuperAdminUpdate(BaseModel):
    """Payload for updating a portal user. All fields are optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, pattern="^(admin|reseller_staff)$")


class SuperAdminResponse(BaseModel):
    """Response shape returned for a SuperAdmin. Never includes password_hash."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ref: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
