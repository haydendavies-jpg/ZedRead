"""Pydantic request/response schemas for the /license-invoices routes."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LicenseInvoiceCreate(BaseModel):
    """Payload for POST /license-invoices — raise an invoice against a license."""

    license_id: uuid.UUID
    amount_cents: int = Field(..., ge=0, description="Invoice amount in cents")
    period_start: datetime
    period_end: datetime


class LicenseInvoicePayRequest(BaseModel):
    """Payload for POST /license-invoices/{id}/pay — mark an invoice as paid."""

    paid_at: datetime | None = None  # Defaults to now() if omitted


class LicenseInvoiceResponse(BaseModel):
    """Serialised LicenseInvoice returned by all /license-invoices routes."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    license_id: uuid.UUID
    amount_cents: int
    status: str
    period_start: datetime
    period_end: datetime
    paid_at: datetime | None
    created_at: datetime
