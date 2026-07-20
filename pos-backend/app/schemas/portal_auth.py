"""Pydantic schemas for portal authentication requests and responses."""

import uuid

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Payload for POST /auth/portal/login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token pair returned on successful login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload for POST /auth/portal/refresh."""

    refresh_token: str


class GrantSummary(BaseModel):
    """Describes one available management grant during scope selection."""

    user_id: uuid.UUID
    grant_id: uuid.UUID
    scope: str
    scope_name: str
    access_profile_name: str


class IdentitySummary(BaseModel):
    """
    Describes one available capability during login disambiguation.

    Returned when a matching User row (or rows sharing an email) offers more
    than one capability — e.g. a "hybrid" row with both superadmin_role and
    at least one portal-capable grant (ROLE_MODEL.md §1/§3). The client
    presents these as a selection screen and calls POST /auth/portal/identity-token
    with the chosen identity_type to continue.
    """

    identity_type: str
    display_name: str


class UnifiedLoginResponse(BaseModel):
    """
    Unified login response covering every User capability: admin-portal role and POS-manager grants.

    For a bare superadmin_role row: access_token and refresh_token are
    populated; all other fields are None (backward-compatible with the
    existing TokenResponse shape).

    For a row with one portal-capable grant: access_token and refresh_token are
    populated alongside user_id and user_name.

    For a row with multiple portal-capable grants: access_token and refresh_token
    are None and available_grants lists the options. The client selects one and
    calls POST /auth/portal/management-token to obtain a token.

    For a row (or rows sharing an email) offering more than one capability:
    access_token and refresh_token are None and available_identities lists the
    options. The client selects one and calls POST /auth/portal/identity-token
    to continue (which may itself return available_grants if the chosen
    capability has multiple portal-capable grants).
    """

    token_type: str = "bearer"
    access_token: str | None = None
    refresh_token: str | None = None
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    available_grants: list[GrantSummary] | None = None
    available_identities: list[IdentitySummary] | None = None


class IdentityTokenRequest(BaseModel):
    """
    Payload for POST /auth/portal/identity-token.

    Used by the frontend identity-selector when a matching row (or rows)
    offers more than one capability. The password is re-verified for the
    chosen identity_type to prevent identity enumeration.
    """

    email: EmailStr
    password: str
    identity_type: str


class ManagementTokenRequest(BaseModel):
    """
    Payload for POST /auth/portal/management-token.

    Used by the frontend scope-selector when a POS user has multiple grants.
    The password is re-verified to prevent grant enumeration (an attacker who
    obtains a partial login response cannot probe grants without knowing the
    password).
    """

    user_id: uuid.UUID
    grant_id: uuid.UUID
    password: str


class MgmtRefreshRequest(BaseModel):
    """Payload for POST /auth/portal/mgmt-refresh."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Payload for POST /auth/portal/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for POST /auth/portal/reset-password."""

    token: str
    new_password: str
