"""Pydantic schemas for the POS settings framework (Android POS Phase 2)."""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.constants.statuses import SettingType


class SettingOut(BaseModel):
    """
    A setting's catalog definition merged with its resolved override state.

    Returned to both the management portal (full override detail, so the
    Settings page can distinguish "inherited from brand" from "overridden
    at this site") and the POS terminal (which only cares about
    effective_value, but gets the same shape for a uniform client model).
    """

    key: str
    label: str
    category: str
    type: SettingType
    options: list[str] | None
    default_value: Any
    brand_value: Any = Field(None, description="The brand-level override, or None if unset")
    site_value: Any = Field(None, description="The site-level override, or None if unset/not applicable")
    effective_value: Any = Field(..., description="site_value, else brand_value, else default_value")


class SettingUpdateRequest(BaseModel):
    """
    Payload for PUT /settings/{key}.

    site_id absent/None sets the brand-level default; a site_id sets that
    site's own override. value is validated against the catalog entry's
    SettingType and options (settings_service._validate_value).
    """

    value: Any
    site_id: uuid.UUID | None = None
