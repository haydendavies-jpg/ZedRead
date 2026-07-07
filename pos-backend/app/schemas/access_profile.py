"""Pydantic schemas for AccessProfile capability-flag requests."""

from pydantic import BaseModel, Field


class AccessProfileCapabilitiesUpdate(BaseModel):
    """Payload for PATCH /access-profiles/{id}/capabilities — Stage 24 open-item flag.

    Both fields are optional — only fields present in model_fields_set are
    written, so callers can update one or both independently.
    """

    can_use_open_item: bool | None = None
    open_item_max_price_cents: int | None = Field(None, ge=0)
