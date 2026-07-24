"""
Catalog of valid PrintTemplateElement.field_key values, scoped per template_type/section.

Mirrors app/constants/settings.py's "catalog lives in code, only overrides are
persisted" convention — the field list itself is never stored in the DB, only
which fields a given template has chosen and how they're styled.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PrintFieldDefinition:
    """One selectable field a template element can be set to."""

    key: str
    label: str
    section: str  # 'header' | 'items' | 'footer'


# ── Header/footer fields — usable on every template_type ────────────────────
_COMMON_HEADER_FOOTER_FIELDS: list[PrintFieldDefinition] = [
    PrintFieldDefinition("LOGO", "Logo", "header"),
    PrintFieldDefinition("BRAND_NAME", "Brand name", "header"),
    PrintFieldDefinition("STORE_NAME", "Store name", "header"),
    PrintFieldDefinition("ADDRESS", "Address", "header"),
    PrintFieldDefinition("STORE_PHONE", "Store phone", "header"),
    PrintFieldDefinition("ABN", "ABN / Tax ID", "header"),
    PrintFieldDefinition("DATE_TIME", "Date/time", "header"),
    PrintFieldDefinition("SERVED_BY", "Served by", "header"),
    PrintFieldDefinition("FREE_TEXT", "Free text", "header"),
    PrintFieldDefinition("DIVIDER", "Divider line", "header"),
    PrintFieldDefinition("LOGO", "Logo", "footer"),
    PrintFieldDefinition("BRAND_NAME", "Brand name", "footer"),
    PrintFieldDefinition("STORE_NAME", "Store name", "footer"),
    PrintFieldDefinition("ADDRESS", "Address", "footer"),
    PrintFieldDefinition("STORE_PHONE", "Store phone", "footer"),
    PrintFieldDefinition("ABN", "ABN / Tax ID", "footer"),
    PrintFieldDefinition("DATE_TIME", "Date/time", "footer"),
    PrintFieldDefinition("SERVED_BY", "Served by", "footer"),
    PrintFieldDefinition("FREE_TEXT", "Free text", "footer"),
    PrintFieldDefinition("DIVIDER", "Divider line", "footer"),
]

# ── Order-related fields — 'invoice' and 'docket' templates only ────────────
_ORDER_HEADER_FOOTER_FIELDS: list[PrintFieldDefinition] = [
    PrintFieldDefinition("INVOICE_NUMBER", "Invoice number", "header"),
    PrintFieldDefinition("ORDER_NOTES", "Order notes", "header"),
    PrintFieldDefinition("INVOICE_NUMBER", "Invoice number", "footer"),
    PrintFieldDefinition("ORDER_NOTES", "Order notes", "footer"),
]
_ORDER_ITEMS_FIELDS: list[PrintFieldDefinition] = [
    PrintFieldDefinition("PRODUCT_LINE", "Product line (name / qty / price)", "items"),
    PrintFieldDefinition("MODIFIER_LINE", "Modifier line", "items"),
    PrintFieldDefinition("ITEM_NOTES", "Item notes", "items"),
]

# ── Type-specific fields ─────────────────────────────────────────────────────
_REGISTER_SUMMARY_FIELDS: list[PrintFieldDefinition] = [
    PrintFieldDefinition("PAYMENT_METHOD_BREAKDOWN", "Payment method breakdown", "items"),
    PrintFieldDefinition("CASH_VARIANCE", "Cash variance", "footer"),
    PrintFieldDefinition("OPENING_CLOSING_CASH", "Opening/closing cash", "footer"),
]
_CASH_IN_SLIP_FIELDS: list[PrintFieldDefinition] = [
    PrintFieldDefinition("CASH_IN_AMOUNT", "Cash-in amount", "footer"),
    PrintFieldDefinition("COUNTED_BY", "Counted by", "footer"),
]

TEMPLATE_TYPE_FIELDS: dict[str, list[PrintFieldDefinition]] = {
    "invoice": _COMMON_HEADER_FOOTER_FIELDS + _ORDER_HEADER_FOOTER_FIELDS + _ORDER_ITEMS_FIELDS,
    "docket": _COMMON_HEADER_FOOTER_FIELDS + _ORDER_HEADER_FOOTER_FIELDS + _ORDER_ITEMS_FIELDS,
    "register_summary": _COMMON_HEADER_FOOTER_FIELDS + _REGISTER_SUMMARY_FIELDS,
    "cash_in_slip": _COMMON_HEADER_FOOTER_FIELDS + _CASH_IN_SLIP_FIELDS,
}

TEMPLATE_TYPES: tuple[str, ...] = ("invoice", "docket", "register_summary", "cash_in_slip")
FONT_SIZES: tuple[str, ...] = ("small", "normal", "large", "xlarge")
ALIGNMENTS: tuple[str, ...] = ("left", "center", "right", "justify")

# Print order for sections — NOT alphabetical ('footer' < 'header' < 'items' would
# print footer content first). Shared by every place that sorts a template's
# elements for rendering (routes/print_templates.py, print_template_service.py).
SECTION_PRINT_ORDER: dict[str, int] = {"header": 0, "items": 1, "footer": 2}

# Default element set seeded onto every new docket template
# (printer_location_service.create_printer_location) and each singleton
# template (print_template_service.seed_default_templates).
DEFAULT_DOCKET_ELEMENTS: list[dict] = [
    {"section": "header", "display_order": 0, "field_key": "STORE_NAME", "alignment": "center", "is_bold": True, "font_size": "large"},
    {"section": "header", "display_order": 1, "field_key": "DATE_TIME", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 2, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "items", "display_order": 0, "field_key": "PRODUCT_LINE", "alignment": "left"},
    {"section": "items", "display_order": 1, "field_key": "MODIFIER_LINE", "alignment": "left", "font_size": "small"},
    {"section": "footer", "display_order": 0, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "footer", "display_order": 1, "field_key": "SERVED_BY", "alignment": "left", "font_size": "small"},
]
DEFAULT_INVOICE_ELEMENTS: list[dict] = [
    {"section": "header", "display_order": 0, "field_key": "LOGO", "alignment": "center"},
    {"section": "header", "display_order": 1, "field_key": "STORE_NAME", "alignment": "center", "is_bold": True, "font_size": "large"},
    {"section": "header", "display_order": 2, "field_key": "ADDRESS", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 3, "field_key": "STORE_PHONE", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 4, "field_key": "ABN", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 5, "field_key": "INVOICE_NUMBER", "alignment": "left", "font_size": "small"},
    {"section": "header", "display_order": 6, "field_key": "DATE_TIME", "alignment": "left", "font_size": "small"},
    {"section": "header", "display_order": 7, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "items", "display_order": 0, "field_key": "PRODUCT_LINE", "alignment": "justify"},
    {"section": "items", "display_order": 1, "field_key": "MODIFIER_LINE", "alignment": "left", "font_size": "small"},
    {"section": "footer", "display_order": 0, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "footer", "display_order": 1, "field_key": "FREE_TEXT", "alignment": "center", "free_text_value": "Thank you!"},
]
DEFAULT_REGISTER_SUMMARY_ELEMENTS: list[dict] = [
    {"section": "header", "display_order": 0, "field_key": "STORE_NAME", "alignment": "center", "is_bold": True},
    {"section": "header", "display_order": 1, "field_key": "FREE_TEXT", "alignment": "center", "free_text_value": "Register Summary"},
    {"section": "header", "display_order": 2, "field_key": "DATE_TIME", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 3, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "items", "display_order": 0, "field_key": "PAYMENT_METHOD_BREAKDOWN", "alignment": "justify"},
    {"section": "footer", "display_order": 0, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "footer", "display_order": 1, "field_key": "OPENING_CLOSING_CASH", "alignment": "justify"},
    {"section": "footer", "display_order": 2, "field_key": "CASH_VARIANCE", "alignment": "justify", "is_bold": True},
]
DEFAULT_CASH_IN_SLIP_ELEMENTS: list[dict] = [
    {"section": "header", "display_order": 0, "field_key": "STORE_NAME", "alignment": "center", "is_bold": True},
    {"section": "header", "display_order": 1, "field_key": "FREE_TEXT", "alignment": "center", "free_text_value": "Cash-in Slip"},
    {"section": "header", "display_order": 2, "field_key": "DATE_TIME", "alignment": "center", "font_size": "small"},
    {"section": "header", "display_order": 3, "field_key": "DIVIDER", "alignment": "center"},
    {"section": "footer", "display_order": 0, "field_key": "CASH_IN_AMOUNT", "alignment": "justify", "is_bold": True},
    {"section": "footer", "display_order": 1, "field_key": "COUNTED_BY", "alignment": "left", "font_size": "small"},
]


def is_valid_field_key(template_type: str, section: str, field_key: str) -> bool:
    """
    Check whether field_key is a valid choice for a template of template_type, in section.

    Args:
        template_type: One of TEMPLATE_TYPES.
        section: 'header' | 'items' | 'footer'.
        field_key: The candidate field key.

    Returns:
        bool: True if the (template_type, section, field_key) combination is valid.
    """
    fields = TEMPLATE_TYPE_FIELDS.get(template_type, [])
    return any(f.section == section and f.key == field_key for f in fields)
