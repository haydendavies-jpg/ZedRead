"""Password hashing (argon2) and JWT token utilities for portal authentication."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

log = structlog.get_logger(__name__)

# Argon2 hasher — default parameters are safe for 2024+ hardware
_hasher = PasswordHasher()

# JWT settings from environment — sensible defaults for local dev
_SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-use-32-plus-chars")
_ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
_ACCESS_TOKEN_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
_REFRESH_TOKEN_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))


def hash_password(plain: str) -> str:
    """
    Hash a plaintext password with argon2id.

    Args:
        plain: The user-supplied plaintext password.

    Returns:
        str: The argon2 hash string (includes algorithm, params, and salt).
    """
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against an argon2 hash.

    Args:
        plain: The user-supplied plaintext password to check.
        hashed: The stored argon2 hash string to compare against.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def _make_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> str:
    """
    Create a signed JWT with standard claims.

    Args:
        subject: The `sub` claim — typically the user UUID string.
        token_type: Either "access" or "refresh" — stored in `type` claim.
        expires_delta: How long until the token expires.
        extra_claims: Optional additional claims to embed (e.g. role).

    Returns:
        str: A signed JWT string.
    """
    now = datetime.now(UTC)
    payload: dict = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),  # Unique token ID — useful for future revocation
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    """
    Create a short-lived access JWT for portal authentication.

    Args:
        user_id: The portal user's UUID as a string.
        role: The user's role string (e.g. "super_admin", "admin").

    Returns:
        str: A signed access JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES),
        extra_claims={"role": role},
    )


def create_pos_access_token(user_id: str, site_id: str, jti: str) -> str:
    """
    Create a short-lived access JWT for an authenticated POS terminal user.

    Embeds site_id and jti so the token is self-contained — the dependency
    can verify site access without an extra query parameter.

    Args:
        user_id: The POS user's UUID as a string.
        site_id: The site UUID the user authenticated against.
        jti: Pre-generated UUID string used as the token ID (matches the
             user_pos_sessions.token_jti column for revocation support).

    Returns:
        str: A signed POS access JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="pos_access",
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES),
        # jti is passed explicitly so it matches the session row written to DB
        extra_claims={"site_id": site_id, "jti": jti},
    )


def create_refresh_token(user_id: str) -> str:
    """
    Create a long-lived refresh JWT for obtaining new access tokens.

    Refresh tokens carry no role — the role is re-read from the DB on refresh
    so role changes take effect without requiring logout.

    Args:
        user_id: The portal user's UUID as a string.

    Returns:
        str: A signed refresh JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=_REFRESH_TOKEN_DAYS),
    )


def decode_token(token: str, expected_type: str) -> dict:
    """
    Decode and validate a JWT, checking its type claim.

    Args:
        token: The raw JWT string to decode.
        expected_type: Either "access" or "refresh" — must match the token's `type` claim.

    Returns:
        dict: The decoded token payload.

    Raises:
        JWTError: If the token is invalid, expired, or the type does not match.
    """
    payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    if payload.get("type") != expected_type:
        # Token type mismatch — e.g. refresh token used where access token is expected
        raise JWTError(f"expected token type '{expected_type}', got '{payload.get('type')}'")
    return payload
