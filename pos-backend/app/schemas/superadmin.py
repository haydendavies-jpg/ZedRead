"""Pydantic schemas for SuperAdmin management requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SuperAdminCreate(BaseModel):
    """
    Payload for creating a new portal user (Admin-role SuperAdmin only).

    password is optional (ROLE_MODEL.md §3 shared-email flow): when the
    email already belongs to another identity (a User or another
    SuperAdmin), the new SuperAdmin links to that existing sign-in
    password instead of being given a new one. create_superadmin()
    enforces the DB-dependent side — a brand-new email still requires a
    password, and a matching email must NOT carry one.
    """

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=6)
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
