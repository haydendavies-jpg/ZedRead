"""Pydantic schemas for PrintTemplate requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.printer_location import PrinterLocationOut


class PrintTemplateElementOut(BaseModel):
    """Serialised template element for API responses."""

    id: uuid.UUID
    section: str
    display_order: int
    field_key: str
    free_text_value: str | None
    font_size: str
    alignment: str
    is_bold: bool
    is_italic: bool

    model_config = {"from_attributes": True}


class PrintTemplateOut(BaseModel):
    """Serialised print template for API responses (no elements — see PrintTemplateDetail)."""

    id: uuid.UUID
    brand_id: uuid.UUID
    printer_location_id: uuid.UUID | None
    template_type: str
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrintTemplateDetail(PrintTemplateOut):
    """PrintTemplateOut plus its ordered elements — the shape the portal editor and POS read."""

    elements: list[PrintTemplateElementOut]


class PrintTemplateUpdate(BaseModel):
    """Payload for renaming a print template. Only name is mutable this way — see replace_elements for content."""

    name: str = Field(..., min_length=1, max_length=255)


class PrintTemplateElementIn(BaseModel):
    """One element in a PUT /print-templates/{id}/elements whole-list replace payload."""

    section: str = Field(..., pattern="^(header|items|footer)$")
    display_order: int = Field(0, ge=0)
    field_key: str = Field(..., min_length=1, max_length=50)
    free_text_value: str | None = None
    font_size: str = Field("normal", pattern="^(small|normal|large|xlarge)$")
    alignment: str = Field("left", pattern="^(left|center|right|justify)$")
    is_bold: bool = False
    is_italic: bool = False


class PrintTemplateElementsReplace(BaseModel):
    """Payload for PUT /print-templates/{id}/elements — the template's complete new element list."""

    elements: list[PrintTemplateElementIn]


class PosCompanyProfileOut(BaseModel):
    """
    Resolved company-profile fields for template rendering — Android has no
    other company-profile fetch, so GET /pos/print-config carries this
    alongside the templates/locations themselves.
    """

    logo_url: str | None
    brand_name: str
    store_name: str
    address: str
    phone: str | None
    abn: str | None


class PosPrintConfigResponse(BaseModel):
    """Response for GET /pos/print-config — everything Android needs to render every template type locally."""

    printer_locations: list[PrinterLocationOut]
    templates: list[PrintTemplateDetail]
    company_profile: PosCompanyProfileOut
