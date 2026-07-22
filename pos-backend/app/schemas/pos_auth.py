"""Pydantic schemas for POS terminal authentication requests and responses."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class POSLoginRequest(BaseModel):
    """
    Payload for POST /auth/pos/login — email+password login for this terminal.

    No site_id here: the site is resolved from the user's own active grants
    (self-service — auto-resolved if there's exactly one, otherwise offered
    via available_sites), not chosen by the caller — see SiteOption /
    POSSiteTokenRequest for the multi-site selection step. device_token is
    this terminal's own previously-claimed token, or None on its very first
    login ever; the server claims (or re-pairs) a device and returns its
    token for the client to persist — see POSLoginResponse.device_token.
    hardware_id is a stable OS-level identifier (Android's
    Settings.Secure.ANDROID_ID) that survives an app reinstall, unlike
    device_token — if the terminal shows up with no device_token but a
    hardware_id matching a previously-claimed device, it's recognised and
    re-linked instead of claiming a brand-new seat.
    """

    email: EmailStr
    password: str
    device_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name for this terminal, used only if a new device is claimed",
    )
    device_token: str | None = Field(
        default=None,
        description="This terminal's own previously-claimed device token, or None on first login",
    )
    hardware_id: str | None = Field(
        default=None,
        max_length=255,
        description="Stable OS-level hardware identifier for this terminal (e.g. Android ID)",
    )


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
    device_name: str = Field(..., min_length=1, max_length=255)
    device_token: str | None = None
    hardware_id: str | None = Field(default=None, max_length=255)
    site_id: uuid.UUID


class POSLoginResponse(BaseModel):
    """
    Response returned by POST /auth/pos/login and POST /auth/pos/site-token.

    Either the token fields are populated (login resolved to a single site),
    or available_sites is populated and the caller must call
    POST /auth/pos/site-token with the chosen site_id — mirrors the portal's
    available_grants selection pattern. Exactly one of the two shapes is
    populated, never both. device_token is the (possibly newly-claimed or
    re-paired) terminal token the client must persist locally and echo back
    on every subsequent login/site-token/pin-verify call.
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
    device_token: str | None = None


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

    email is optional: the real switch-operator flow asks staff for a PIN
    only, matching real POS terminal conventions (no re-typing an email each
    time) — omitting it verifies the PIN against every active user granted
    at site_id instead of one disambiguated account. Supplying it keeps the
    original, slightly cheaper single-account check for any caller that
    already knows which user is switching in.
    """

    email: EmailStr | None = None
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
    session without requiring a full email+password login. email is included
    so a caller that verified by PIN alone (no email in the request) can
    still persist which account is now active locally — nullable since
    users.email itself is nullable (e.g. an auto-created Master User).
    """

    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    user_name: str
    email: EmailStr | None
    access_profile_name: str
    is_pin_reset_required: bool


class POSLogoutResponse(BaseModel):
    """Response returned on successful POS logout — confirms the session was ended."""

    detail: str = "Logged out"
