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


class PortalUserRole(str, Enum):
    """Access roles for the super-admin portal."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    RESELLER = "reseller"
