"""Pydantic schemas for POS terminal authentication requests and responses."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class POSLoginRequest(BaseModel):
    """Payload for POST /auth/pos/login — email+password login for a specific site."""

    email: EmailStr
    password: str
    site_id: uuid.UUID


class POSLoginResponse(BaseModel):
    """
    Response returned on successful POS login.

    Contains the access token and enough context for the terminal to display
    the user and site without additional API calls.
    """

    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    user_name: str
    site_id: uuid.UUID
    site_name: str
    access_profile_name: str
    is_pin_reset_required: bool


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
