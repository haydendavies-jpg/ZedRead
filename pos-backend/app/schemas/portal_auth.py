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


class UnifiedLoginResponse(BaseModel):
    """
    Unified login response covering both portal users and POS manager users.

    For portal users: access_token and refresh_token are populated; all other
    fields are None (backward-compatible with the existing TokenResponse shape).

    For POS manager users with one grant: access_token and refresh_token are
    populated alongside user_id and user_name.

    For POS manager users with multiple grants: access_token and refresh_token
    are None and available_grants lists the options. The client selects one and
    calls POST /auth/portal/management-token to obtain a token.
    """

    token_type: str = "bearer"
    access_token: str | None = None
    refresh_token: str | None = None
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    available_grants: list[GrantSummary] | None = None


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
