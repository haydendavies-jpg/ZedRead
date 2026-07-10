"""Unit tests for the Stage 19 XLSX parsing/coercion helpers in import_service.py.

No database required — these test the pure parsing and value-coercion logic
in isolation, per tests_CLAUDE.md's guidance for pure functions.
"""

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.import_service import (
    _clean_str,
    _error_message,
    _parse_bool,
    _parse_int,
    _parse_price_cents,
    parse_xlsx,
)


def _workbook_bytes(headers: list[str], rows: list[list]) -> bytes:
    """Build minimal XLSX bytes with a header row and the given data rows."""
    import io

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ── parse_xlsx ────────────────────────────────────────────────────────────────


def test_parse_xlsx_returns_lowercased_headers():
    """Header cells are lowercased and trimmed for case-insensitive matching."""
    file_bytes = _workbook_bytes(["Ref", " Name ", "Price"], [["CAT-000001", "Burger", "9.99"]])
    headers, rows = parse_xlsx(file_bytes)
    assert headers == ["ref", "name", "price"]
    assert rows == [{"ref": "CAT-000001", "name": "Burger", "price": "9.99"}]


def test_parse_xlsx_skips_fully_blank_rows():
    """A row with every cell blank is dropped rather than producing an empty dict."""
    file_bytes = _workbook_bytes(["ref", "name"], [[None, None], ["CAT-000001", "Burger"]])
    headers, rows = parse_xlsx(file_bytes)
    assert len(rows) == 1
    assert rows[0]["name"] == "Burger"


def test_parse_xlsx_empty_sheet_returns_no_rows():
    """A workbook with only a header row (or none) yields an empty row list."""
    file_bytes = _workbook_bytes(["ref", "name"], [])
    headers, rows = parse_xlsx(file_bytes)
    assert headers == ["ref", "name"]
    assert rows == []


def test_parse_xlsx_invalid_bytes_raises_invalid_workbook_error():
    """Bytes that aren't a real XLSX file raise InvalidWorkbookError."""
    from app.services.import_service import InvalidWorkbookError

    with pytest.raises(InvalidWorkbookError):
        parse_xlsx(b"not an xlsx file")


# ── Value coercion helpers ────────────────────────────────────────────────────


def test_clean_str_trims_and_treats_blank_as_none():
    assert _clean_str("  Burger  ") == "Burger"
    assert _clean_str("") is None
    assert _clean_str("   ") is None
    assert _clean_str(None) is None


@pytest.mark.parametrize("raw,expected", [("TRUE", True), ("false", False), ("1", True), ("0", False), ("yes", True), ("no", False)])
def test_parse_bool_accepts_common_representations(raw, expected):
    assert _parse_bool(raw) is expected


def test_parse_bool_passes_through_native_bool():
    """openpyxl may hand back a real Python bool for checkbox-like cells."""
    assert _parse_bool(True) is True


def test_parse_bool_blank_is_none():
    assert _parse_bool(None) is None
    assert _parse_bool("") is None


def test_parse_bool_invalid_value_raises_value_error():
    with pytest.raises(ValueError):
        _parse_bool("maybe")


def test_parse_int_parses_numeric_strings():
    assert _parse_int("12") == 12
    assert _parse_int(7) == 7
    assert _parse_int(None) is None
    assert _parse_int("") is None


def test_parse_int_invalid_value_raises_value_error():
    with pytest.raises(ValueError):
        _parse_int("not a number")


def test_parse_price_cents_converts_dollars_to_cents():
    assert _parse_price_cents("9.99") == 999
    assert _parse_price_cents("10") == 1000
    assert _parse_price_cents(None) is None
    assert _parse_price_cents("") is None


def test_parse_price_cents_rounds_half_up():
    """A third decimal place rounds half up rather than truncating."""
    assert _parse_price_cents("9.995") == 1000


def test_parse_price_cents_invalid_value_raises_value_error():
    with pytest.raises(ValueError):
        _parse_price_cents("free")


def test_error_message_extracts_http_exception_detail():
    exc = HTTPException(status_code=400, detail="Category belongs to a different brand")
    assert _error_message(exc) == "Category belongs to a different brand"


def test_error_message_stringifies_value_error():
    assert _error_message(ValueError("Unknown category 'Drinks'")) == "Unknown category 'Drinks'"
