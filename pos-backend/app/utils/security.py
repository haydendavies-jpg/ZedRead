"""Password hashing (argon2) and JWT token utilities for portal authentication."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

log = structlog.get_logger(__name__)

# Argon2 hasher — default parameters are safe for 2024+ hardware.
# Cost params are env-overridable so the test suite can run with a cheap,
# insecure hasher (hundreds of hash_password() calls across fixtures/tests
# would otherwise each pay the ~50-100ms production cost). Defaults below
# match argon2-cffi's own PasswordHasher() defaults, so production/dev
# behaviour is unchanged when the env vars are unset.
_hasher = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST", "65536")),
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "4")),
)

# Built-in placeholder — safe for local dev, MUST be overridden in any real
# deployment. validate_secret_key() refuses to start the server if this value
# (or one that is too short) is still in effect outside dev/test.
_SECRET_KEY_PLACEHOLDER: str = "change-me-in-production-use-32-plus-chars"

# Minimum acceptable secret length for a non-dev environment. HS256 keys shorter
# than 32 bytes materially weaken the signature against offline brute-forcing.
_MIN_SECRET_KEY_LENGTH: int = 32

# Environment names treated as non-production — the insecure-default check is
# skipped for these so local dev and the test suite run without extra config.
_DEV_ENVIRONMENTS: frozenset[str] = frozenset({"development", "dev", "local", "test", "testing"})

# JWT settings from environment — sensible defaults for local dev
_SECRET_KEY: str = os.getenv("SECRET_KEY", _SECRET_KEY_PLACEHOLDER)
_ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
_ACCESS_TOKEN_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
_REFRESH_TOKEN_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# POS terminal tokens intentionally do not expire on a short clock: a terminal
# is expected to stay signed in for an entire shift (or longer), and revocation
# is already handled independently of expiry — logout ends the token's
# user_pos_sessions row (_check_pos_session_row), and license/device state is
# re-checked on every request. A ~10-year TTL keeps the JWT's "exp" claim
# structurally present without it ever being the thing that logs someone out.
_POS_ACCESS_TOKEN_DAYS: int = int(os.getenv("POS_ACCESS_TOKEN_EXPIRE_DAYS", "3650"))


def normalize_email(email: str) -> str:
    """
    Normalize an email address for storage and comparison.

    Login/identity lookups must be case-insensitive — every write path calls
    this before persisting so stored values are consistently lowercased, and
    every lookup normalizes its input the same way. Whitespace is stripped
    too, since a pasted email commonly carries leading/trailing spaces.

    Args:
        email: The raw email address as typed/submitted.

    Returns:
        str: The trimmed, lowercased email.
    """
    return email.strip().lower()


def validate_secret_key(environment: str, secret_key: str | None = None) -> None:
    """
    Refuse to start with an insecure JWT signing key in a non-dev environment.

    The signing key protects every access, refresh, management, POS, and
    impersonation token. If the built-in placeholder is left in place in
    production, anyone who has read the (public) source can forge a valid
    admin token, so a misconfigured deployment must fail loudly at startup
    rather than boot with a known key.

    Dev and test environments are exempt so local runs and CI need no extra
    configuration.

    Args:
        environment: The deployment environment name (e.g. "production").
            Matched case-insensitively against the dev/test allowlist.
        secret_key: The key to validate. Defaults to the module's configured
            SECRET_KEY; accepted as an argument to keep the check unit-testable.

    Raises:
        RuntimeError: If, outside dev/test, the key is unset/placeholder or
            shorter than the minimum length.
    """
    # Fall back to the process-wide configured key when no explicit value is given
    key = secret_key if secret_key is not None else _SECRET_KEY

    # Local dev and CI are allowed to run on the placeholder — skip the check
    if environment.strip().lower() in _DEV_ENVIRONMENTS:
        return

    if not key or key == _SECRET_KEY_PLACEHOLDER:
        raise RuntimeError(
            "SECRET_KEY is unset or still uses the built-in placeholder. "
            "Set a strong, unique SECRET_KEY (32+ characters) before starting "
            f"in environment '{environment}'."
        )

    if len(key) < _MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY is too short ({len(key)} chars); it must be at least "
            f"{_MIN_SECRET_KEY_LENGTH} characters in environment '{environment}'."
        )


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


async def verify_password_async(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against an argon2 hash without blocking the event loop.

    Argon2 verification is deliberately CPU-expensive (~50-100 ms). Called
    directly inside an async route it freezes the single event loop for that
    entire time, stalling every other in-flight request. Login and PIN-verify
    paths run constantly (and are attacker-facing), so they must use this
    wrapper; rare admin-time hashing (user create, password set) may stay on
    the sync verify_password()/hash_password() for simplicity.

    Args:
        plain: The user-supplied plaintext password to check.
        hashed: The stored argon2 hash string to compare against.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return await asyncio.to_thread(verify_password, plain, hashed)


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


def create_access_token(user_id: str, role: str, token_version: int = 0) -> str:
    """
    Create a short-lived access JWT for portal authentication.

    Args:
        user_id: The portal user's UUID as a string.
        role: The user's role string (e.g. "admin", "reseller_staff").
        token_version: The admin's current token_version, embedded as the 'tv'
            claim so the token is revoked when the column is bumped.

    Returns:
        str: A signed access JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=_ACCESS_TOKEN_MINUTES),
        extra_claims={"role": role, "tv": token_version},
    )


def create_pos_access_token(
    user_id: str, site_id: str, jti: str, device_id: str | None = None
) -> str:
    """
    Create a long-lived access JWT for an authenticated POS terminal user.

    Unlike portal/management tokens, this does not expire on a short clock —
    a terminal is meant to stay signed in for a whole shift or longer, and
    revocation runs independently of the token's own expiry (logout ends the
    matching user_pos_sessions row; see _check_pos_session_row).

    Embeds site_id, device_id, and jti so the token is self-contained — the
    dependency can verify site/device access without an extra query parameter.

    Args:
        user_id: The POS user's UUID as a string.
        site_id: The site UUID the user authenticated against.
        jti: Pre-generated UUID string used as the token ID (matches the
             user_pos_sessions.token_jti column for revocation support).
        device_id: The PosDevice UUID the session was opened from, or None
            when the caller has no device context (e.g. a PIN-verify switch
            that didn't supply a device_token) — register-session-gated
            routes reject a token with no device_id.

    Returns:
        str: A signed POS access JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="pos_access",
        expires_delta=timedelta(days=_POS_ACCESS_TOKEN_DAYS),
        # jti is passed explicitly so it matches the session row written to DB
        extra_claims={"site_id": site_id, "device_id": device_id, "jti": jti},
    )


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    """
    Create a long-lived refresh JWT for obtaining new access tokens.

    Refresh tokens carry no role — the role is re-read from the DB on refresh
    so role changes take effect without requiring logout.

    Args:
        user_id: The portal user's UUID as a string.
        token_version: The admin's current token_version, embedded as 'tv' so a
            bump (password change/reset, logout) invalidates the refresh token.

    Returns:
        str: A signed refresh JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=_REFRESH_TOKEN_DAYS),
        extra_claims={"tv": token_version},
    )


def create_mgmt_access_token(
    user_id: str,
    scope: str,
    grant_id: str,
    site_id: str | None,
    brand_id: str | None,
    group_id: str | None,
    token_version: int = 0,
) -> str:
    """
    Create a management access JWT for backend portal authentication.

    Embeds the grant_id so resolve_management_access() can load the grant
    in one query without re-resolving scope. Expiry is 60 minutes — longer
    than the 15-min POS terminal token because portal sessions are interactive.

    Args:
        user_id: The POS user's UUID string.
        scope: Grant scope value — 'site', 'brand', or 'group'.
        grant_id: UUID of the active UserAccessGrant that authorises this session.
        site_id: Site UUID string (set only when scope='site').
        brand_id: Brand UUID string (set only when scope='brand' or 'site').
        group_id: Group UUID string (set only when scope='group').
        token_version: The user's current token_version, embedded as 'tv' so a
            bump (logout-everywhere) revokes the token.

    Returns:
        str: A signed management access JWT.
    """
    extra: dict = {"scope": scope, "grant_id": grant_id, "tv": token_version}
    if site_id:
        extra["site_id"] = site_id
    if brand_id:
        extra["brand_id"] = brand_id
    if group_id:
        extra["group_id"] = group_id
    return _make_token(
        subject=user_id,
        token_type="mgmt_access",
        expires_delta=timedelta(minutes=60),
        extra_claims=extra,
    )


def create_impersonation_token(
    user_id: str,
    scope: str,
    grant_id: str,
    site_id: str | None,
    brand_id: str | None,
    group_id: str | None,
    admin_id: str,
    admin_email: str,
    admin_name: str,
    token_version: int = 0,
) -> str:
    """
    Create a management access JWT for an admin impersonation session.

    Identical to create_mgmt_access_token() but embeds imp_id, imp_email,
    and imp_name claims so resolve_management_access() can attribute all
    actions to the admin rather than the entity's master user.

    Args:
        user_id: Master user's UUID string (entity being impersonated).
        scope: Grant scope — 'site', 'brand', or 'group'.
        grant_id: UUID of the active grant for the impersonated entity.
        site_id: Site UUID string (set only when scope='site').
        brand_id: Brand UUID string (set only when scope='brand' or 'site').
        group_id: Group UUID string (set only when scope='group').
        admin_id: UUID string of the portal admin (User) performing impersonation.
        admin_email: Snapshotted email of the impersonating admin.
        admin_name: Snapshotted display name of the impersonating admin.

    Returns:
        str: A signed management access JWT with impersonation claims.
    """
    extra: dict = {
        "scope": scope,
        "grant_id": grant_id,
        "tv": token_version,
        "imp_id": admin_id,
        "imp_email": admin_email,
        "imp_name": admin_name,
    }
    if site_id:
        extra["site_id"] = site_id
    if brand_id:
        extra["brand_id"] = brand_id
    if group_id:
        extra["group_id"] = group_id
    return _make_token(
        subject=user_id,
        token_type="mgmt_access",
        expires_delta=timedelta(minutes=60),
        extra_claims=extra,
    )


def create_mgmt_refresh_token(user_id: str, token_version: int = 0) -> str:
    """
    Create a long-lived refresh JWT for management portal session renewal.

    Args:
        user_id: The POS user's UUID string.
        token_version: The user's current token_version, embedded as 'tv' so a
            bump (logout-everywhere) invalidates the refresh token.

    Returns:
        str: A signed management refresh JWT.
    """
    return _make_token(
        subject=user_id,
        token_type="mgmt_refresh",
        expires_delta=timedelta(days=_REFRESH_TOKEN_DAYS),
        extra_claims={"tv": token_version},
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
