"""
License-plan page gating (ROLE_MODEL.md §4 — "licensing gate, orthogonal to role permissions").

A page is visible to a User only if their AccessProfile grants it AND the
site's license plan allows it: `visible = has_role_permission AND license_allows`.

LICENSE_PLAN_PAGES maps a known plan_name to the page keys it unlocks. An
unrecognised plan_name (License.plan_name is a free-form string, not an
enum — see DATA_MODEL.md) is treated as unrestricted, since the absence of
a tier mapping should never silently lock out pages on a plan nobody has
classified yet; only the three named tiers below are deliberately limited.
"""

from app.constants.pages import PAGE_KEYS

STARTER_PLAN_PAGES: frozenset[str] = frozenset(
    {
        "products",
        "categories",
        "reporting_groups",
        "site_settings",
        "daily_sales",
        "invoices",
        "users",
        "customers",
    }
)

PRO_PLAN_PAGES: frozenset[str] = frozenset(
    {
        "products",
        "variants_modifiers",
        "combos",
        "categories",
        "reporting_groups",
        "menu_builder",
        "menus",
        "site_settings",
        "devices",
        "tax_settings",
        "license_billing",
        "daily_sales",
        "tax_collected",
        "invoices",
        "audit_log",
        "users",
        "access_grants",
        "customers",
        "loyalty_programs",
    }
)

# Enterprise (and any other named tier) unlocks the full catalog.
ENTERPRISE_PLAN_PAGES: frozenset[str] = PAGE_KEYS

LICENSE_PLAN_PAGES: dict[str, frozenset[str]] = {
    "starter": STARTER_PLAN_PAGES,
    "pro": PRO_PLAN_PAGES,
    "enterprise": ENTERPRISE_PLAN_PAGES,
}


def allowed_pages_for_plan(plan_name: str | None) -> frozenset[str]:
    """
    Return the set of page keys a license plan unlocks.

    Args:
        plan_name: The site's License.plan_name (case-insensitive), or None
            if the site has no active license.

    Returns:
        frozenset[str]: Page keys this plan allows. Falls back to the full
        catalog for None or any plan_name not in LICENSE_PLAN_PAGES, since
        only the three named tiers above are deliberately restricted.
    """
    if plan_name is None:
        return PAGE_KEYS
    return LICENSE_PLAN_PAGES.get(plan_name.strip().lower(), PAGE_KEYS)
