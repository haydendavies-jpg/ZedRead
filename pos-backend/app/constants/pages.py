"""
Page catalog for the portal's page-category permission hierarchy (ROLE_MODEL.md §4).

Each page belongs to exactly one category. A category tab is shown to a User
if at least one page within it is granted on their AccessProfile (and that
page is not hidden by the site's license plan — see
app/constants/license_plans.py). This module is the single source of truth
for valid page_key values; AccessProfilePagePermission rows are validated
against it.

This list is intentionally open-ended — add new (key, category, label)
entries here as new portal pages ship. Do not hardcode page keys elsewhere.
"""

from app.constants.statuses import PageCategory

# (page_key, category, label)
PAGE_CATALOG: list[tuple[str, PageCategory, str]] = [
    # Product & Menus
    ("products", PageCategory.PRODUCT_MENUS, "Products"),
    ("variants_modifiers", PageCategory.PRODUCT_MENUS, "Variants & Modifiers"),
    ("combos", PageCategory.PRODUCT_MENUS, "Combos"),
    ("categories", PageCategory.PRODUCT_MENUS, "Categories"),
    ("reporting_groups", PageCategory.PRODUCT_MENUS, "Reporting Groups"),
    ("menu_builder", PageCategory.PRODUCT_MENUS, "Menu Builder"),
    ("menus", PageCategory.PRODUCT_MENUS, "Menus"),
    # App Configuration
    ("site_settings", PageCategory.APP_CONFIGURATION, "Site Settings"),
    ("devices", PageCategory.APP_CONFIGURATION, "Devices"),
    ("tax_settings", PageCategory.APP_CONFIGURATION, "Tax Settings"),
    ("license_billing", PageCategory.APP_CONFIGURATION, "License & Billing"),
    # Reports
    ("daily_sales", PageCategory.REPORTS, "Daily Sales"),
    ("tax_collected", PageCategory.REPORTS, "Tax Collected"),
    ("invoices", PageCategory.REPORTS, "Invoices"),
    ("audit_log", PageCategory.REPORTS, "Audit Log"),
    # User Management
    ("users", PageCategory.USER_MANAGEMENT, "Users"),
    ("access_grants", PageCategory.USER_MANAGEMENT, "Users & Access"),
    ("access_profiles", PageCategory.USER_MANAGEMENT, "Access Profiles"),
    # Customers & Loyalty
    ("customers", PageCategory.CUSTOMERS_LOYALTY, "Customers"),
    ("loyalty_programs", PageCategory.CUSTOMERS_LOYALTY, "Loyalty Programs"),
]

PAGE_KEYS: frozenset[str] = frozenset(key for key, _, _ in PAGE_CATALOG)

PAGE_CATEGORY_BY_KEY: dict[str, PageCategory] = {key: category for key, category, _ in PAGE_CATALOG}


def pages_in_category(category: PageCategory) -> list[str]:
    """
    Return all page keys belonging to a given category.

    Args:
        category: The page category to filter by.

    Returns:
        list[str]: Page keys in that category, in catalog order.
    """
    return [key for key, cat, _ in PAGE_CATALOG if cat == category]
