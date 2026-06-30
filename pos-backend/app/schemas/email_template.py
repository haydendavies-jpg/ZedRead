"""Pydantic schemas for EmailTemplate requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EmailTemplateCreate(BaseModel):
    """Payload for creating a new email template."""

    template_key: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)


class EmailTemplateUpdate(BaseModel):
    """Payload for updating an email template. All fields are optional.

    template_key is intentionally not editable — other services look templates
    up by this stable key (e.g. branding_service's billing-info-request flow).
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    is_active: bool | None = Field(default=None)


class EmailTemplateResponse(BaseModel):
    """Response shape returned for an EmailTemplate."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    template_key: str
    name: str
    subject: str
    body: str
    is_system: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
