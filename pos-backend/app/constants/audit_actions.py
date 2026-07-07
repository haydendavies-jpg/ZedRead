"""
Audit action string constants used by log_action().

Every constant is a dot-separated lowercase string following the pattern
resource.action or resource.action.outcome (see app_CLAUDE.md section 9.3).

Add constants here as new stages are built. Never hardcode action strings
in service files — always import from this module (CLAUDE.md absolute rule 8).
"""

# ── Phase 1 / Stage 2 — Portal Authentication ────────────────────────────────
AUTH_LOGIN_SUCCESS = "auth.login.success"
AUTH_LOGIN_FAILED = "auth.login.failed"
AUTH_TOKEN_REFRESHED = "auth.token.refreshed"
AUTH_LOGOUT = "auth.logout"
AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset.requested"
AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset.completed"
AUTH_PASSWORD_CHANGED = "auth.password.changed"

# ── Phase 1 / Stage 3 — Hierarchy CRUD ───────────────────────────────────────
GROUP_CREATED = "group.created"
GROUP_UPDATED = "group.updated"
GROUP_SUSPENDED = "group.suspended"
GROUP_ACTIVATED = "group.activated"

BRAND_CREATED = "brand.created"
BRAND_UPDATED = "brand.updated"
BRAND_SUSPENDED = "brand.suspended"
BRAND_ACTIVATED = "brand.activated"

SITE_CREATED = "site.created"
SITE_UPDATED = "site.updated"
SITE_SUSPENDED = "site.suspended"
SITE_ACTIVATED = "site.activated"

GROUP_LOGO_UPDATED = "group.logo.updated"
BRAND_LOGO_UPDATED = "brand.logo.updated"
SITE_LOGO_UPDATED = "site.logo.updated"

HIERARCHY_WIPED = "hierarchy.wiped"  # Admin CLI: hard-delete of all Groups/Brands/Sites and dependents

PORTAL_USER_CREATED = "superadmin.created"
PORTAL_USER_UPDATED = "superadmin.updated"
PORTAL_USER_SUSPENDED = "superadmin.suspended"
PORTAL_USER_ACTIVATED = "superadmin.activated"

# ── Phase 1 / Stage 4 — License Management ───────────────────────────────────
LICENSE_CREATED = "license.created"
LICENSE_UPDATED = "license.updated"
LICENSE_ENABLED = "license.enabled"
LICENSE_DISABLED = "license.disabled"
LICENSE_EXPIRED = "license.expired"

LICENSE_INVOICE_PAID = "license_invoice.paid"

DEVICE_REGISTERED = "device.registered"
DEVICE_DEREGISTERED = "device.deregistered"

# ── Phase 2 / Stage 7 — POS Authentication ───────────────────────────────────
POS_LOGIN_SUCCESS = "pos_auth.login.success"
POS_LOGIN_FAILED = "pos_auth.login.failed"
POS_LOGOUT = "pos_auth.logout"
POS_PIN_SET = "pos_auth.pin.set"
POS_PIN_RESET = "pos_auth.pin.reset"
POS_PIN_VERIFIED = "pos_auth.pin.verified"

USER_CREATED = "user.created"
USER_UPDATED = "user.updated"
USER_DEACTIVATED = "user.deactivated"
USER_INVITED = "user.invited"
USER_INVITE_ACCEPTED = "user.invite.accepted"
USER_PIN_ADMIN_SET = "user.pin.admin_set"  # Portal admin sets a PIN on behalf of a POS user
USER_BACKEND_ROLE_UPDATED = "user.backend_role.updated"

# ── Phase 2 / Stage 8 — Product Catalog ──────────────────────────────────────
PRODUCT_CREATED = "product.created"
PRODUCT_UPDATED = "product.updated"
PRODUCT_PRICE_CHANGED = "product.price.changed"  # Separate constant — high-value event
PRODUCT_DEACTIVATED = "product.deactivated"
PRODUCT_PHOTO_UPDATED = "product.photo.updated"

CATEGORY_CREATED = "category.created"
CATEGORY_UPDATED = "category.updated"
CATEGORY_DELETED = "category.deleted"

TAX_CATEGORY_CREATED = "tax_category.created"
TAX_CATEGORY_UPDATED = "tax_category.updated"
TAX_RATE_CREATED = "tax_rate.created"
TAX_RATE_UPDATED = "tax_rate.updated"

TAX_TEMPLATE_CREATED = "tax_template.created"
TAX_TEMPLATE_UPDATED = "tax_template.updated"
TAX_TEMPLATE_DELETED = "tax_template.deleted"
TAX_TEMPLATE_RATE_CREATED = "tax_template_rate.created"
TAX_TEMPLATE_RATE_UPDATED = "tax_template_rate.updated"
TAX_TEMPLATE_RATE_DELETED = "tax_template_rate.deleted"

SITE_PRODUCT_OVERRIDE_SET = "site_product_override.set"
SITE_PRODUCT_OVERRIDE_REMOVED = "site_product_override.removed"

VARIANT_CREATED = "variant.created"
VARIANT_UPDATED = "variant.updated"
VARIANT_DEACTIVATED = "variant.deactivated"

MODIFIER_GROUP_CREATED = "modifier_group.created"
MODIFIER_GROUP_UPDATED = "modifier_group.updated"
MODIFIER_OPTION_CREATED = "modifier_option.created"
MODIFIER_OPTION_UPDATED = "modifier_option.updated"
PRODUCT_MODIFIER_LINKED = "product.modifier.linked"
PRODUCT_MODIFIER_UNLINKED = "product.modifier.unlinked"

COMBO_GROUP_CREATED = "combo_group.created"
COMBO_OPTION_ADDED = "combo_option.added"
COMBO_OPTION_REMOVED = "combo_option.removed"

# ── Phase 3 / Stage 10 — Invoice Engine ──────────────────────────────────────
INVOICE_CREATED = "invoice.created"

# ── Phase 4 / Stage 13 — Management Access ───────────────────────────────────
MGMT_LOGIN_SUCCESS = "mgmt_auth.login.success"
MGMT_LOGIN_FAILED = "mgmt_auth.login.failed"
MGMT_TOKEN_ISSUED = "mgmt_auth.token.issued"
ACCESS_GRANT_CREATED = "access_grant.created"
ACCESS_GRANT_REVOKED = "access_grant.revoked"
ACCESS_GRANT_DEFAULT_SET = "access_grant.default_set"
ACCESS_PROFILE_PORTAL_UPDATED = "access_profile.portal_access.updated"
ACCESS_GRANT_BACKEND_ROLE_UPDATED = "access_grant.backend_role.updated"
ACCESS_PROFILE_PAGE_GRANTED = "access_profile.page.granted"
ACCESS_PROFILE_PAGE_REVOKED = "access_profile.page.revoked"
ACCESS_PROFILE_CAPABILITIES_UPDATED = "access_profile.capabilities.updated"
INVOICE_LINE_ITEM_ADDED = "invoice.line_item.added"
INVOICE_PAID = "invoice.paid"
INVOICE_VOIDED = "invoice.voided"
INVOICE_REFUNDED = "invoice.refunded"
INVOICE_DISCOUNT_APPLIED = "invoice.discount.applied"

# ── Phase 5 / Stage 15 — Company Profile & Billing Info Requests ────────────
BILLING_INFO_REQUESTED = "billing_info.requested"
EMAIL_TEMPLATE_CREATED = "email_template.created"
EMAIL_TEMPLATE_UPDATED = "email_template.updated"

# ── Phase 5 / Stage 15 — Admin Impersonation ─────────────────────────────────
ADMIN_IMPERSONATION_STARTED = "admin.impersonation.started"
