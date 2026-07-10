"""Pydantic schemas for the Stage 19 bulk XLSX import/export response contract."""

import uuid

from pydantic import BaseModel


class ImportRowError(BaseModel):
    """A single row that failed validation and was skipped during an import."""

    row_number: int
    message: str


class ImportSummary(BaseModel):
    """
    Result of a bulk XLSX import.

    Rows that pass validation are upserted and counted in created/updated;
    rows that fail are skipped (not applied) and reported in errors so the
    rest of the sheet still imports instead of the whole upload failing.
    """

    import_id: uuid.UUID
    created: int
    updated: int
    errors: list[ImportRowError]

    model_config = {"from_attributes": True}
