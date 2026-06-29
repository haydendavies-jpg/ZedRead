"""Pydantic schemas for user invite requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class InviteCreateRequest(BaseModel):
    """Payload for POST /invites — send a new POS user invitation."""

    email: EmailStr
    site_id: uuid.UUID
    access_profile_id: uuid.UUID


class InviteResponse(BaseModel):
    """Response returned when an invite is created."""

    id: uuid.UUID
    email: str
    brand_id: uuid.UUID
    site_id: uuid.UUID
    access_profile_id: uuid.UUID
    is_accepted: bool
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteAcceptRequest(BaseModel):
    """Payload for POST /invites/accept — accept an invite and create the POS user account."""

    token: str
    first_name: str
    last_name: str
    password: str
