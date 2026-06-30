"""Pydantic schemas for reference-data responses."""

from pydantic import BaseModel


class TaxIdLabelResponse(BaseModel):
    """Response shape for the country-driven tax ID label lookup."""

    label: str
