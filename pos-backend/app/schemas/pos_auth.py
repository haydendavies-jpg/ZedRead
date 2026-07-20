"""Pydantic schemas for POS terminal authentication requests and responses."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class POSLoginRequest(BaseModel):
    """
    Payload for POST /auth/pos/login — email+password login for this terminal.

    No site_id here: the site is resolved from the device's own paired site
    (device_token) and the user's grants, not chosen by the caller — see
    SiteOption / POSSiteTokenRequest for the multi-site selection step.
    """

    email: EmailStr
    password: str
    device_token: str


class SiteOption(BaseModel):
    """One selectable site returned when a login can't resolve to a single site."""

    site_id: uuid.UUID
    site_name: str


class POSSiteTokenRequest(BaseModel):
    """
    Payload for POST /auth/pos/site-token — finalizes a multi-site login.

    Re-verifies credentials (same idempotent pattern as the portal's
    management-token step) rather than trusting a bare site_id, since no
    intermediate token is issued between /login and this call.
    """

    email: EmailStr
    password: str
    device_token: str
    site_id: uuid.UUID


class POSLoginResponse(BaseModel):
    """
    Response returned by POST /auth/pos/login and POST /auth/pos/site-token.

    Either the token fields are populated (login resolved to a single site),
    or available_sites is populated and the caller must call
    POST /auth/pos/site-token with the chosen site_id — mirrors the portal's
    available_grants selection pattern. Exactly one of the two shapes is
    populated, never both.
    """

    access_token: str | None = None
    token_type: str = "bearer"
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    site_id: uuid.UUID | None = None
    site_name: str | None = None
    access_profile_name: str | None = None
    is_pin_reset_required: bool | None = None
    available_sites: list[SiteOption] | None = None


class PINSetRequest(BaseModel):
    """Payload for POST /auth/pos/pin/set — set or replace the caller's PIN."""

    pin: str = Field(
        ...,
        min_length=4,
        max_length=6,
        pattern=r"^\d{4,6}$",
        description="4–6 digit numeric PIN",
    )


class PINVerifyRequest(BaseModel):
    """
    Payload for POST /auth/pos/pin/verify — quick PIN check for terminal switch-user.

    Used when a different user wants to take over the terminal without the
    current user logging out (e.g. manager override at the cashier screen).
    """

    email: EmailStr
    pin: str = Field(
        ...,
        min_length=4,
        max_length=6,
        pattern=r"^\d{4,6}$",
        description="4–6 digit numeric PIN",
    )
    site_id: uuid.UUID
    device_token: str | None = Field(
        default=None,
        description=(
            "The terminal's device_token, so the switched-in session keeps "
            "device context (register-session gating, sync). Optional for "
            "backward compatibility with callers that don't yet send it."
        ),
    )


class PINVerifyResponse(BaseModel):
    """
    Response returned on successful PIN verification.

    Issues a fresh POS access token so the incoming user becomes the active
    session without requiring a full email+password login.
    """

    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    user_name: str
    access_profile_name: str
    is_pin_reset_required: bool


class POSLogoutResponse(BaseModel):
    """Response returned on successful POS logout — confirms the session was ended."""

    detail: str = "Logged out"
