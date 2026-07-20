"""Pydantic schemas for POS register (till) sessions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RegisterSessionOpenRequest(BaseModel):
    """
    Payload for POST /register-sessions/open.

    No device field — the device is resolved from the authenticated POS
    token's device_id claim (see POSAccess.device), not re-supplied here.
    """

    opened_at: datetime = Field(..., description="Device-local timestamp the session was opened")
    opening_cash_cents: int = Field(..., ge=0, description="Cash counted into the till at start of shift")


class RegisterSessionCloseRequest(BaseModel):
    """Payload for POST /register-sessions/{session_id}/close."""

    closed_at: datetime = Field(..., description="Device-local timestamp the session was closed")
    closing_cash_cents: int = Field(..., ge=0, description="Cash counted out of the till at close")


class RegisterSessionOut(BaseModel):
    """Full register session state, returned to both the POS terminal and the portal report."""

    id: uuid.UUID
    device_id: uuid.UUID
    site_id: uuid.UUID
    status: str
    opened_at: datetime
    opening_cash_cents: int
    opened_by_user_id: uuid.UUID | None
    opened_by_name: str
    closed_at: datetime | None
    closing_cash_cents: int | None
    expected_cash_cents: int | None
    variance_cents: int | None
    closed_by_user_id: uuid.UUID | None
    closed_by_name: str | None

    model_config = {"from_attributes": True}
