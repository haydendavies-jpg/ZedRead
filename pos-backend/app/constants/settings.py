"""
Setting catalog for the POS settings framework (Android POS Phase 2).

Mirrors app/constants/pages.py's pattern: the catalog of valid setting keys
lives in code (not a database table), so it can be searched, validated, and
extended without a migration; only the per-brand/per-site *overrides* live in
the setting_values table (see app/models/setting_value.py). A row with no
override falls back to another row's override (site → brand) and finally to
this catalog's default_value.

Add new settings here as new stages need them. Never hardcode a setting key
string elsewhere — import SETTING_KEYS/get_setting_definition from this module.
"""

from dataclasses import dataclass

from app.constants.statuses import SettingType


@dataclass(frozen=True)
class SettingDefinition:
    """One entry in the setting catalog — the static shape of a setting."""

    key: str
    label: str
    category: str
    type: SettingType
    default_value: object
    # Valid choices for single_select/multi_select settings; None for boolean/datetime.
    options: list[str] | None = None
    description: str = ""


# Ordered by category, then key — searchable by name/label/category on both
# the portal and POS surfaces (see settings_service.search_setting_definitions()).
SETTING_CATALOG: list[SettingDefinition] = [
    SettingDefinition(
        key="cash_in_mode",
        label="Cash-in entry mode",
        category="Register",
        type=SettingType.SINGLE_SELECT,
        # User-testing feedback: the full per-denomination cash count should
        # be the out-of-box default, not the single bulk-total entry — a site
        # can still opt back into "bulk" from the portal's settings page.
        default_value="denomination",
        options=["bulk", "denomination"],
        description=(
            "How start-of-day/end-of-day cash is entered on the POS: a single bulk "
            "total, or a per-denomination breakdown grid."
        ),
    ),
    SettingDefinition(
        key="hide_variance_on_close",
        label="Hide variance on cash-up",
        category="Register",
        type=SettingType.BOOLEAN,
        default_value=False,
        description=(
            "When enabled, the end-of-day cash-up screen shows the counted total "
            "only — the expected/variance comparison is hidden from the cashier."
        ),
    ),
    SettingDefinition(
        key="auto_menu_enabled",
        label="Auto Menu",
        category="Menu Studio",
        type=SettingType.BOOLEAN,
        default_value=False,
        description=(
            "When enabled, the Android Register's menu selector offers an "
            "unfiltered 'All items' option showing the full catalog. When "
            "disabled (the default), staff may only browse the menu layouts "
            "actually published from Menu Studio."
        ),
    ),
    SettingDefinition(
        key="auto_print_docket_on_hold",
        label="Auto-print docket on Hold",
        category="Printing",
        type=SettingType.BOOLEAN,
        default_value=True,
        description=(
            "When enabled, order dockets print automatically to each item's printer "
            "location as soon as an order is held (sent to the kitchen before payment)."
        ),
    ),
    SettingDefinition(
        key="auto_print_docket_on_pay",
        label="Auto-print docket on Pay",
        category="Printing",
        type=SettingType.BOOLEAN,
        default_value=True,
        description=(
            "When enabled, order dockets print automatically to each item's printer "
            "location when a sale is paid directly, without ever being held first."
        ),
    ),
]

SETTING_KEYS: frozenset[str] = frozenset(s.key for s in SETTING_CATALOG)

_SETTING_BY_KEY: dict[str, SettingDefinition] = {s.key: s for s in SETTING_CATALOG}


def get_setting_definition(key: str) -> SettingDefinition | None:
    """
    Look up a setting's catalog definition by key.

    Args:
        key: The setting key to look up.

    Returns:
        SettingDefinition | None: The definition, or None if key is not a
            recognised setting.
    """
    return _SETTING_BY_KEY.get(key)


def search_setting_definitions(search: str | None) -> list[SettingDefinition]:
    """
    Return catalog definitions matching a case-insensitive substring search.

    Matches against key, label, and category — powers the "searchable by
    name/label/category" requirement on both the portal and POS surfaces.

    Args:
        search: The search term, or None/blank to return the full catalog.

    Returns:
        list[SettingDefinition]: Matching definitions, catalog order.
    """
    if not search:
        return list(SETTING_CATALOG)
    needle = search.strip().lower()
    if not needle:
        return list(SETTING_CATALOG)
    return [
        s
        for s in SETTING_CATALOG
        if needle in s.key.lower() or needle in s.label.lower() or needle in s.category.lower()
    ]
