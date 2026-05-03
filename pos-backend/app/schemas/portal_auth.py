"""Pydantic schemas for portal authentication requests and responses."""

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
