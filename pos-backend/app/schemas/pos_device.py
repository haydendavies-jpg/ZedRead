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
    hardware_id: str | None = Field(
        default=None, max_length=255, description="Stable OS-level hardware identifier (Android ID), if known"
    )


class PosDeviceUpdate(BaseModel):
    """Payload for PATCH /pos-devices/{id} and PATCH /pos-devices/management/{id} — rename a device."""

    device_name: str = Field(..., min_length=1, max_length=255)


class PosDeviceResponse(BaseModel):
    """Serialised PosDevice returned by all /pos-devices routes."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    site_id: uuid.UUID
    license_id: uuid.UUID
    device_name: str
    device_token: str
    hardware_id: str | None
    is_active: bool
    registered_at: datetime


class PosDeviceDeleteResponse(BaseModel):
    """Response for DELETE /pos-devices/{id} — a hard delete, summarising what was cascaded."""

    id: uuid.UUID
    register_sessions_deleted: int = Field(
        ..., description="Register sessions belonging to this device that were deleted to allow it"
    )
    invoices_detached: int = Field(
        ..., description="Invoices whose register_session_id was cleared because their session was deleted"
    )
