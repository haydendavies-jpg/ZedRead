"""ORM model registry — import all models here so Alembic autogenerate detects them."""

from app.models.access_profile import AccessProfile
from app.models.access_profile_page_permission import AccessProfilePagePermission
from app.models.audit_log import AuditLog
from app.models.brand import Brand
from app.models.category import Category
from app.models.email_template import EmailTemplate
from app.models.group import Group
from app.models.invoice import Invoice
from app.models.invoice_line_item import InvoiceLineItem
from app.models.invoice_line_modifier import InvoiceLineModifier
from app.models.invoice_tax_breakdown import InvoiceTaxBreakdown
from app.models.license import License
from app.models.license_invoice import LicenseInvoice
from app.models.menu import Menu
from app.models.menu_button import MenuButton
from app.models.menu_layout import MenuLayout
from app.models.menu_tab import MenuTab
from app.models.modifier_group import ModifierGroup
from app.models.modifier_option import ModifierOption
from app.models.modifier_option_group_link import ModifierOptionGroupLink
from app.models.payment import Payment
from app.models.superadmin import SuperAdmin
from app.models.pos_device import PosDevice
from app.models.user import User
from app.models.product import Product
from app.models.product_attribute_type import ProductAttributeType
from app.models.product_attribute_value import ProductAttributeValue
from app.models.product_combo_group import ProductComboGroup
from app.models.product_combo_option import ProductComboOption
from app.models.product_modifier_group_link import ProductModifierGroupLink
from app.models.product_variant import ProductVariant
from app.models.product_variant_attribute import ProductVariantAttribute
from app.models.reporting_group import ReportingGroup
from app.models.site import Site
from app.models.site_product_override import SiteProductOverride
from app.models.site_variant_override import SiteVariantOverride
from app.models.tax_category import TaxCategory
from app.models.tax_rate import TaxRate
from app.models.tax_template import TaxTemplate
from app.models.tax_template_rate import TaxTemplateRate
from app.models.user_access_grant import UserAccessGrant
from app.models.user_invite import UserInvite
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession

__all__ = [
    "AccessProfile",
    "AccessProfilePagePermission",
    "AuditLog",
    "Brand",
    "Category",
    "EmailTemplate",
    "Group",
    "Invoice",
    "InvoiceLineItem",
    "InvoiceLineModifier",
    "InvoiceTaxBreakdown",
    "License",
    "LicenseInvoice",
    "Menu",
    "MenuButton",
    "MenuLayout",
    "MenuTab",
    "ModifierGroup",
    "ModifierOption",
    "ModifierOptionGroupLink",
    "Payment",
    "SuperAdmin",
    "PosDevice",
    "User",
    "Product",
    "ProductAttributeType",
    "ProductAttributeValue",
    "ProductComboGroup",
    "ProductComboOption",
    "ProductModifierGroupLink",
    "ProductVariant",
    "ProductVariantAttribute",
    "ReportingGroup",
    "Site",
    "SiteProductOverride",
    "SiteVariantOverride",
    "TaxCategory",
    "TaxRate",
    "TaxTemplate",
    "TaxTemplateRate",
    "UserAccessGrant",
    "UserInvite",
    "UserPIN",
    "UserPOSSession",
]
