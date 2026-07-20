"""Pydantic schemas for User management — POS staff, delegated onboarding, and admin-portal rows.

SuperAdmin access is a role on User (`superadmin_role`), not a separate
identity type — schemas that used to live in schemas/superadmin.py are
folded in here, alongside the schemas that previously lived inline in
routes/users.py (project convention: schemas live in schemas/, not routes/).
"""

import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Valid superadmin_role values — mirrors SuperAdminRole in app/constants/statuses.py
_SUPERADMIN_ROLES = {"admin", "reseller_staff"}


class ManagedUserCreate(BaseModel):
    """
    Payload for a management-portal (or portal admin) caller creating a new User
    plus their initial access grant in one step (Users page "Add User").

    Mirrors AccessGrantCreate's scope/site_id/brand_id FK-consistency rule.
    Group scope is intentionally not offered here — a group-scope User is
    only ever the auto-created Master User (site_service.create_site()); this
    endpoint is for ordinary staff onboarded at a brand or site. Never
    exposes superadmin_role — that's only settable via the admin-portal-only
    POST/PATCH /users routes (ROLE_MODEL.md §1).
    """

    first_name: str
    last_name: str
    email: EmailStr | None = None
    password: str | None = None
    scope: str
    site_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    access_profile_id: uuid.UUID
    backend_role: str | None = None

    @model_validator(mode="after")
    def check_password_requires_email(self) -> "ManagedUserCreate":
        """A password is meaningless without a login email to attach it to."""
        if self.password is not None and self.email is None:
            raise ValueError("password requires an email")
        return self

    @model_validator(mode="after")
    def check_scope_fk_consistency(self) -> "ManagedUserCreate":
        """Ensure exactly one FK matches the scope value — site or brand only."""
        if self.scope == "site":
            if not self.site_id or self.brand_id:
                raise ValueError("scope='site' requires site_id only")
        elif self.scope == "brand":
            if not self.brand_id or self.site_id:
                raise ValueError("scope='brand' requires brand_id only")
        else:
            raise ValueError(f"scope must be 'site' or 'brand'; got '{self.scope}'")
        return self


class SiteGrantSummary(BaseModel):
    """Minimal site grant info embedded in UserOut for the portal UI."""

    grant_id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    is_default: bool
    access_profile_name: str
    can_access_portal: bool


class UserOut(BaseModel):
    """User response schema — active site grants, brand/group info, portal/admin access flags."""

    id: uuid.UUID
    ref: str
    # None for group-scoped master users (brand_id is NULL for them) and for
    # a pure admin-portal row with no tenant scope at all.
    brand_id: uuid.UUID | None = None
    brand_name: str = ""
    group_name: str = ""
    name: str
    # None for Master Users, whose `name` is the site's name rather than a person's
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    backend_role: str | None = None
    # 'admin' | 'reseller_staff' | None — admin-portal role, orthogonal to tenant grants
    superadmin_role: str | None = None
    is_active: bool
    # Active site-scope grants with grant ID, site info, and default flag
    site_grants: list[SiteGrantSummary] = []
    # True when at least one active grant uses a portal-capable access profile
    has_portal_access: bool = False

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    """
    Request body for creating a User from the admin portal.

    email/password are optional at creation (ROLE_MODEL.md §2 — only
    required once the user is granted backend access), except when
    superadmin_role is set, where email (and a 12+ character password,
    unless linking to an existing identity's password) is required —
    admin-portal access has no other login path.

    Email-without-password is permitted specifically to support linking to
    an existing sign-in password: when the email already belongs to another
    row, the new row is linked to that existing password rather than being
    given a new one. The route (create_user) enforces the DB-dependent side
    of this: a brand-new email still requires a password, and a matching
    email must NOT carry one.

    brand_id is optional — omit it (together with superadmin_role) to create
    a pure admin-portal row with no tenant scope at all.
    """

    brand_id: str | None = None
    first_name: str
    last_name: str
    email: EmailStr | None = None
    password: str | None = None
    superadmin_role: str | None = None

    @model_validator(mode="after")
    def _password_requires_email(self) -> "UserCreate":
        """A password is meaningless without a login email to attach it to."""
        if self.password is not None and self.email is None:
            raise ValueError("password requires an email")
        return self

    @model_validator(mode="after")
    def _superadmin_role_valid(self) -> "UserCreate":
        """Reject an unrecognised superadmin_role value."""
        if self.superadmin_role is not None and self.superadmin_role not in _SUPERADMIN_ROLES:
            raise ValueError(f"superadmin_role must be one of: {sorted(_SUPERADMIN_ROLES)} or null")
        return self

    @model_validator(mode="after")
    def _superadmin_requires_email(self) -> "UserCreate":
        """Admin-portal access has no login path other than email+password."""
        if self.superadmin_role is not None and self.email is None:
            raise ValueError("email is required for a superadmin_role user")
        return self

    @model_validator(mode="after")
    def _superadmin_password_length(self) -> "UserCreate":
        """A fresh password for a superadmin_role row must meet the stricter admin-portal bar."""
        if self.superadmin_role is not None and self.password is not None and len(self.password) < 12:
            raise ValueError("password must be at least 12 characters for a superadmin_role user")
        return self


class EmailCheckOut(BaseModel):
    """
    Whether an email is already registered, for the create-user form.

    Lets the portal detect an existing identity as the admin types and skip
    the password field (the new User will share the existing password).
    """

    exists: bool
    display_name: str | None = None
    # False when the matching identity has no password set (a passwordless POS
    # user) — the form must then still collect one.
    has_password: bool = False


class UserUpdate(BaseModel):
    """
    Request body for editing a User — all fields optional.

    password is write-only (never echoed back on UserOut) and, for now, may
    only be supplied by a single portal admin — see _PASSWORD_SET_ALLOWED_EMAIL
    in routes/users.py.
    """

    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    backend_role: str | None = None  # Use sentinel to distinguish "not supplied" from "clear"
    # Admin-portal role — same "not supplied" vs "clear" sentinel as backend_role
    superadmin_role: str | None = None
    password: str | None = Field(default=None, min_length=8)

    model_config = {"from_attributes": True}


class SetPinRequest(BaseModel):
    """Request body for an admin setting a POS user's PIN."""

    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        """Enforce 4–6 digit numeric PIN."""
        if not re.fullmatch(r"\d{4,6}", v):
            raise ValueError("PIN must be 4–6 digits")
        return v


class EnrichedGrantOut(BaseModel):
    """Full grant row enriched with scope entity names, for the edit-user panel."""

    grant_id: uuid.UUID
    scope: str
    # Site scope fields
    site_id: uuid.UUID | None = None
    site_name: str | None = None
    # Brand scope fields (present for site- and brand-scope grants)
    brand_id: uuid.UUID | None = None
    brand_name: str | None = None
    # Group scope fields (present for all grants)
    group_id: uuid.UUID | None = None
    group_name: str | None = None
    # Access profile
    access_profile_id: uuid.UUID
    access_profile_name: str
    can_access_portal: bool
    is_default: bool
    is_active: bool


class GroupScopeEntry(BaseModel):
    """One row in the group-access overview: group, brand, or site with current grant state."""

    scope: str  # 'group', 'brand', or 'site'
    # NULL for group-scope rows; set for brand and site rows
    brand_id: uuid.UUID | None = None
    brand_name: str | None = None
    site_id: uuid.UUID | None = None
    site_name: str | None = None
    # NULL means no active grant for this scope/entity
    grant_id: uuid.UUID | None = None
    access_profile_id: uuid.UUID | None = None
    access_profile_name: str | None = None
    can_access_portal: bool = False
    is_default: bool = False
    backend_role: str | None = None


class GroupAccessOut(BaseModel):
    """All brands and sites in the user's group with their current access state."""

    group_id: uuid.UUID
    group_name: str
    entries: list[GroupScopeEntry]
