"""Pydantic request/response schemas for the /pos-devices routes."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PosDeviceRegister(BaseModel):
    """Payload for POST /pos-devices — register a new POS terminal."""

    site_id: uuid.UUID
    license_id: uuid.UUID
    device_name: str = Field(..., min_length=1, max_length=255)
    device_token: str = Field(..., min_length=8, max_length=255, description="Unique hardware token from the device")


class PosDeviceResponse(BaseModel):
    """Serialised PosDevice returned by all /pos-devices routes."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    site_id: uuid.UUID
    license_id: uuid.UUID
    device_name: str
    device_token: str
    is_active: bool
    registered_at: datetime
