"""Shared XLSX export service for Products, Categories, and Reporting Groups (Stage 19).

Builds two kinds of workbook, both re-importable via import_service.py:
  - Template: header row + one example row + data-validation dropdowns for any
    foreign-key-ish column (category name, reporting group name).
  - Full export: the brand's current data for that entity.

Column headers are the shared contract with import_service.py — a header must
match exactly (case-insensitive) for that column to be recognised on import.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product
from app.models.reporting_group import ReportingGroup

# Header order is the on-disk column order for both template and full export.
PRODUCT_COLUMNS: list[str] = [
    "ref",
    "name",
    "category",
    "description",
    "print_name",
    "price",
    "is_taxable",
    "is_open_item",
    "display_order",
    "is_active",
]
CATEGORY_COLUMNS: list[str] = ["ref", "name", "reporting_group", "display_order", "is_active"]
REPORTING_GROUP_COLUMNS: list[str] = ["ref", "name"]

_BOOL_LABELS = {True: "TRUE", False: "FALSE"}


def _cents_to_dollars_str(cents: int) -> str:
    """
    Format a cents integer as a plain decimal dollar string, e.g. 1500 -> "15.00".

    Args:
        cents: Amount in cents (BIGINT storage, CLAUDE.md rule 4).

    Returns:
        str: Dollar amount with exactly two decimal places.
    """
    dollars = (Decimal(cents) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{dollars:.2f}"


def _rows_to_workbook(headers: list[str], data_rows: list[dict[str, Any]], sheet_title: str) -> Workbook:
    """
    Write a header row plus data rows to a single-sheet workbook.

    Args:
        headers: Column header strings, in order.
        data_rows: Each dict maps a header to its cell value for that row.
        sheet_title: Name of the worksheet.

    Returns:
        Workbook: An in-memory openpyxl workbook, ready for data validation or streaming.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    ws.freeze_panes = "A2"
    for row in data_rows:
        ws.append([row.get(h, "") for h in headers])
    return wb


def _add_name_dropdown(wb: Workbook, ws_title: str, column_index: int, options: list[str], max_rows: int = 1000) -> None:
    """
    Attach an Excel data-validation dropdown of existing names to a column.

    Options are written to a hidden helper sheet and referenced by range,
    since a literal inline list is capped at 255 characters by Excel and
    brands may have far more categories/reporting groups than that allows.

    Args:
        wb: The workbook to modify.
        ws_title: Title of the sheet the dropdown applies to.
        column_index: 1-based column index the dropdown is attached to.
        options: Valid option strings (e.g. existing category names).
        max_rows: How many data rows (below the header) get the dropdown applied.
    """
    if not options:
        return

    helper_title = f"_{ws_title}_lists"[:31]
    helper = wb.create_sheet(title=helper_title)
    for i, option in enumerate(options, start=1):
        helper.cell(row=i, column=column_index, value=option)
    helper.sheet_state = "hidden"

    from openpyxl.utils import get_column_letter

    col_letter = get_column_letter(column_index)
    formula = f"{helper_title}!${col_letter}$1:${col_letter}${len(options)}"
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True)
    dv.error = "Select a value from the dropdown list"
    dv.errorTitle = "Invalid value"

    ws = wb[ws_title]
    dv.add(f"{col_letter}2:{col_letter}{max_rows}")
    ws.add_data_validation(dv)


def workbook_to_bytes(wb: Workbook) -> bytes:
    """
    Serialise a workbook to raw XLSX bytes for streaming in an HTTP response.

    Args:
        wb: The workbook to serialise.

    Returns:
        bytes: Raw .xlsx file content.
    """
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def _category_names(db: AsyncSession, brand_id: uuid.UUID) -> list[str]:
    """Return active category names for a brand, alphabetically, for dropdown options."""
    result = await db.execute(
        select(Category.name)
        .where(Category.brand_id == brand_id, Category.is_active == True)  # noqa: E712
        .order_by(Category.name)
    )
    return [row[0] for row in result.all()]


async def _reporting_group_names(db: AsyncSession, brand_id: uuid.UUID) -> list[str]:
    """Return reporting group names for a brand, alphabetically, for dropdown options."""
    result = await db.execute(
        select(ReportingGroup.name).where(ReportingGroup.brand_id == brand_id).order_by(ReportingGroup.name)
    )
    return [row[0] for row in result.all()]


# ── Products ──────────────────────────────────────────────────────────────────


async def export_products(db: AsyncSession, brand_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    Fetch all active products for a brand as export-ready rows keyed by PRODUCT_COLUMNS.

    Args:
        db: Active database session.
        brand_id: Brand to export products for.

    Returns:
        list[dict]: One dict per product, ordered by display_order then name.
    """
    result = await db.execute(
        select(Product, Category.name)
        .join(Category, Product.category_id == Category.id)
        .where(Product.brand_id == brand_id, Product.is_active == True)  # noqa: E712
        .order_by(Product.display_order, Product.name)
    )
    rows: list[dict[str, Any]] = []
    for product, category_name in result.all():
        rows.append(
            {
                "ref": product.ref,
                "name": product.name,
                "category": category_name,
                "description": product.description or "",
                "print_name": product.print_name or "",
                "price": _cents_to_dollars_str(product.base_price_cents),
                "is_taxable": _BOOL_LABELS[product.is_taxable],
                "is_open_item": _BOOL_LABELS[product.is_open_item],
                "display_order": product.display_order,
                "is_active": _BOOL_LABELS[product.is_active],
            }
        )
    return rows


async def build_products_template(db: AsyncSession, brand_id: uuid.UUID) -> Workbook:
    """
    Build a Products import template: header + one example row + category dropdown.

    Args:
        db: Active database session.
        brand_id: Brand the template's dropdown options are scoped to.

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    category_names = await _category_names(db, brand_id)
    example = {
        "ref": "",
        "name": "Example Product",
        "category": category_names[0] if category_names else "Uncategorised",
        "description": "",
        "print_name": "",
        "price": "9.99",
        "is_taxable": "TRUE",
        "is_open_item": "FALSE",
        "display_order": "0",
        "is_active": "TRUE",
    }
    wb = _rows_to_workbook(PRODUCT_COLUMNS, [example], "Products")
    _add_name_dropdown(wb, "Products", PRODUCT_COLUMNS.index("category") + 1, category_names)
    return wb


async def build_products_export(db: AsyncSession, brand_id: uuid.UUID) -> Workbook:
    """
    Build a full Products export workbook with the brand's current catalog data.

    Args:
        db: Active database session.
        brand_id: Brand to export.

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    rows = await export_products(db, brand_id)
    category_names = await _category_names(db, brand_id)
    wb = _rows_to_workbook(PRODUCT_COLUMNS, rows, "Products")
    _add_name_dropdown(wb, "Products", PRODUCT_COLUMNS.index("category") + 1, category_names, max_rows=max(len(rows) + 500, 1000))
    return wb


# ── Categories ────────────────────────────────────────────────────────────────


async def export_categories(db: AsyncSession, brand_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    Fetch all categories for a brand as export-ready rows keyed by CATEGORY_COLUMNS.

    Args:
        db: Active database session.
        brand_id: Brand to export categories for.

    Returns:
        list[dict]: One dict per category, ordered by display_order then name.
    """
    result = await db.execute(
        select(Category, ReportingGroup.name)
        .join(ReportingGroup, Category.reporting_group_id == ReportingGroup.id)
        .where(Category.brand_id == brand_id)
        .order_by(Category.display_order, Category.name)
    )
    rows: list[dict[str, Any]] = []
    for category, reporting_group_name in result.all():
        rows.append(
            {
                "ref": category.ref,
                "name": category.name,
                "reporting_group": reporting_group_name,
                "display_order": category.display_order,
                "is_active": _BOOL_LABELS[category.is_active],
            }
        )
    return rows


async def build_categories_template(db: AsyncSession, brand_id: uuid.UUID) -> Workbook:
    """
    Build a Categories import template: header + one example row + reporting group dropdown.

    Args:
        db: Active database session.
        brand_id: Brand the template's dropdown options are scoped to.

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    reporting_group_names = await _reporting_group_names(db, brand_id)
    example = {
        "ref": "",
        "name": "Example Category",
        "reporting_group": reporting_group_names[0] if reporting_group_names else "",
        "display_order": "0",
        "is_active": "TRUE",
    }
    wb = _rows_to_workbook(CATEGORY_COLUMNS, [example], "Categories")
    _add_name_dropdown(wb, "Categories", CATEGORY_COLUMNS.index("reporting_group") + 1, reporting_group_names)
    return wb


async def build_categories_export(db: AsyncSession, brand_id: uuid.UUID) -> Workbook:
    """
    Build a full Categories export workbook with the brand's current categories.

    Args:
        db: Active database session.
        brand_id: Brand to export.

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    rows = await export_categories(db, brand_id)
    reporting_group_names = await _reporting_group_names(db, brand_id)
    wb = _rows_to_workbook(CATEGORY_COLUMNS, rows, "Categories")
    _add_name_dropdown(
        wb,
        "Categories",
        CATEGORY_COLUMNS.index("reporting_group") + 1,
        reporting_group_names,
        max_rows=max(len(rows) + 500, 1000),
    )
    return wb


# ── Reporting Groups ──────────────────────────────────────────────────────────


async def export_reporting_groups(db: AsyncSession, brand_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    Fetch all reporting groups for a brand as export-ready rows keyed by REPORTING_GROUP_COLUMNS.

    Args:
        db: Active database session.
        brand_id: Brand to export reporting groups for.

    Returns:
        list[dict]: One dict per reporting group, default group first.
    """
    result = await db.execute(
        select(ReportingGroup)
        .where(ReportingGroup.brand_id == brand_id)
        .order_by(ReportingGroup.is_default.desc(), ReportingGroup.name)
    )
    return [{"ref": group.ref, "name": group.name} for group in result.scalars().all()]


async def build_reporting_groups_template() -> Workbook:
    """
    Build a Reporting Groups import template: header + one example row (no FK columns).

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    example = {"ref": "", "name": "Example Reporting Group"}
    return _rows_to_workbook(REPORTING_GROUP_COLUMNS, [example], "Reporting Groups")


async def build_reporting_groups_export(db: AsyncSession, brand_id: uuid.UUID) -> Workbook:
    """
    Build a full Reporting Groups export workbook with the brand's current groups.

    Args:
        db: Active database session.
        brand_id: Brand to export.

    Returns:
        Workbook: Ready to stream as an .xlsx download.
    """
    rows = await export_reporting_groups(db, brand_id)
    return _rows_to_workbook(REPORTING_GROUP_COLUMNS, rows, "Reporting Groups")
