"""Status value enums and constants used across the application.

Import from this module rather than using raw strings for status comparisons
(CLAUDE.md absolute rule 8 — never hardcode status values).
"""

from enum import Enum


class ActorType(str, Enum):
    """
    Identifies the type of actor that performed an audited action.

    USER is a human portal or POS user.
    SYSTEM is an automated process such as the nightly licence expiry Celery task.
    """

    USER = "user"
    SYSTEM = "system"


class ActiveStatus(str, Enum):
    """Generic active/suspended status used on Group, Brand, and Site."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class LicenseStatus(str, Enum):
    """Lifecycle states for a licence record."""

    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"


class InvoiceStatus(str, Enum):
    """Lifecycle states for an invoice."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOIDED = "voided"


class InvoiceType(str, Enum):
    """Distinguishes a standard sale from a refund invoice."""

    SALE = "sale"
    REFUND = "refund"


class PaymentMethod(str, Enum):
    """Accepted payment methods at the POS terminal."""

    CASH = "cash"
    CARD = "card"
    VOUCHER = "voucher"
    SPLIT = "split"


class TaxModel(str, Enum):
    """How tax is applied to a line item price."""

    INCLUSIVE = "inclusive"   # Tax is already included in the displayed price
    EXCLUSIVE = "exclusive"   # Tax is added on top of the displayed price
    COMPOUND = "compound"     # GST on base, then PST on base (not on GST-inclusive)


class SuperAdminRole(str, Enum):
    """Access roles for the super-admin portal."""

    ADMIN = "admin"
    RESELLER_STAFF = "reseller_staff"


class SystemAccessProfile(str, Enum):
    """
    Names of the system access profiles seeded for every new brand.

    These are the 5 target roles in ROLE_MODEL.md. MASTER defines the
    permission tier only — the *User* holding it is restricted to exactly
    one per site (assigned automatically when the site is created, see
    site_service.create_site()), unlike the other four which any number of
    Users can hold.

    Created automatically by seed_system_profiles() in access_profile_service.py
    and cannot be deleted (is_system=True).
    """

    ADMIN = "Admin"
    REPORTING_ONLY = "Reporting Only"
    MANAGER = "Manager"
    STAFF = "Staff"
    MASTER = "Master User"


class GrantScope(str, Enum):
    """
    Scope level of a UserAccessGrant.

    SITE: grant covers a single site (original behaviour).
    BRAND: grant covers all sites within a brand (portal management access).
    GROUP: grant covers all brands and sites within a group (portal management access).
    """

    SITE = "site"
    BRAND = "brand"
    GROUP = "group"
