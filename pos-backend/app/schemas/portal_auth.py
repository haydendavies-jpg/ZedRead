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

    grant_id: uuid.UUID
    scope: str
    scope_name: str
    access_profile_name: str


class IdentitySummary(BaseModel):
    """
    Describes one available identity during cross-identity login disambiguation.

    Returned when an email is shared by both a SuperAdmin and a User account
    with at least one portal-capable grant (ROLE_MODEL.md §3). The client
    presents these as a selection screen and calls POST /auth/portal/identity-token
    with the chosen identity_type to continue.
    """

    identity_type: str
    display_name: str


class UnifiedLoginResponse(BaseModel):
    """
    Unified login response covering SuperAdmins and POS manager Users.

    For SuperAdmins: access_token and refresh_token are populated; all other
    fields are None (backward-compatible with the existing TokenResponse shape).

    For Users with one portal-capable grant: access_token and refresh_token are
    populated alongside user_id and user_name.

    For Users with multiple portal-capable grants: access_token and refresh_token
    are None and available_grants lists the options. The client selects one and
    calls POST /auth/portal/management-token to obtain a token.

    For an email shared by both a SuperAdmin and a User: access_token and
    refresh_token are None and available_identities lists the two identity
    options. The client selects one and calls POST /auth/portal/identity-token
    to continue (which may itself return available_grants if the chosen User
    identity has multiple portal-capable grants).
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

    Used by the frontend identity-selector when an email is shared by both a
    SuperAdmin and a portal-capable User. The password is re-verified for the
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
