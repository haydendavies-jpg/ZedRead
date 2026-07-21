"""Unit tests for app/utils/security.py.

Tests cover password hashing (argon2) and JWT token creation/validation.
No database is required — these are pure function tests.
"""

from datetime import UTC, datetime, timedelta

import pytest
from jose import JWTError, jwt

from app.utils.security import (
    _ALGORITHM,
    _MIN_SECRET_KEY_LENGTH,
    _SECRET_KEY,
    _SECRET_KEY_PLACEHOLDER,
    create_access_token,
    create_pos_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_secret_key,
    verify_password,
)


# ── Password hashing ──────────────────────────────────────────────────────────


def test_hash_password_returns_argon2_string():
    """hash_password() returns an argon2 hash string (not plaintext)."""
    hashed = hash_password("MySecretPassword!")
    assert hashed != "MySecretPassword!"
    assert hashed.startswith("$argon2")


def test_verify_password_correct_returns_true():
    """verify_password() returns True for a matching plaintext + hash pair."""
    hashed = hash_password("CorrectPassword!")
    assert verify_password("CorrectPassword!", hashed) is True


def test_verify_password_wrong_returns_false():
    """verify_password() returns False when the password does not match the hash."""
    hashed = hash_password("CorrectPassword!")
    assert verify_password("WrongPassword!", hashed) is False


def test_hash_same_password_produces_different_hashes():
    """Two calls to hash_password() with the same input produce different hashes (salted)."""
    h1 = hash_password("SamePassword!")
    h2 = hash_password("SamePassword!")
    assert h1 != h2
    # Both should still verify correctly
    assert verify_password("SamePassword!", h1) is True
    assert verify_password("SamePassword!", h2) is True


# ── JWT tokens ────────────────────────────────────────────────────────────────


def test_create_access_token_decodes_with_correct_claims():
    """create_access_token() embeds user_id, role, and type='access' in the payload."""
    user_id = "abc-123"
    token = create_access_token(user_id=user_id, role="admin")
    payload = decode_token(token, expected_type="access")

    assert payload["sub"] == user_id
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_create_refresh_token_decodes_with_correct_claims():
    """create_refresh_token() embeds user_id and type='refresh' — no role claim."""
    user_id = "xyz-789"
    token = create_refresh_token(user_id=user_id)
    payload = decode_token(token, expected_type="refresh")

    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"
    assert "role" not in payload  # Refresh tokens carry no role


def test_decode_token_wrong_type_raises():
    """decode_token() raises JWTError when the token type does not match expected_type."""
    access_token = create_access_token("user-1", "admin")

    with pytest.raises(JWTError):
        # Access token passed where refresh token is expected
        decode_token(access_token, expected_type="refresh")


def test_decode_token_invalid_jwt_raises():
    """decode_token() raises JWTError for a malformed token string."""
    with pytest.raises(JWTError):
        decode_token("not.a.real.jwt", expected_type="access")


def test_access_token_different_from_refresh_token():
    """Access and refresh tokens for the same user are not the same string."""
    user_id = "user-99"
    access = create_access_token(user_id, "admin")
    refresh = create_refresh_token(user_id)
    assert access != refresh


def test_create_pos_access_token_decodes_with_correct_claims():
    """create_pos_access_token() embeds site_id, device_id, jti, and type='pos_access'."""
    user_id = "pos-user-1"
    token = create_pos_access_token(user_id, site_id="site-1", jti="jti-1", device_id="device-1")
    payload = decode_token(token, expected_type="pos_access")

    assert payload["sub"] == user_id
    assert payload["site_id"] == "site-1"
    assert payload["device_id"] == "device-1"
    assert payload["jti"] == "jti-1"


def test_create_pos_access_token_does_not_expire_on_a_short_clock():
    """POS terminal tokens stay valid for years, not minutes — revocation is
    session-based (user_pos_sessions), not TTL-based, so a terminal shouldn't
    be forced to re-authenticate mid-shift."""
    token = create_pos_access_token("pos-user-2", site_id="site-1", jti="jti-2")
    # Decode without going through decode_token() so we can inspect the raw exp claim
    payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)

    assert expires_at - datetime.now(UTC) > timedelta(days=365)


# ── SECRET_KEY validation (fail-fast) ─────────────────────────────────────────

# A key long enough to satisfy the minimum-length rule
_STRONG_KEY = "x" * _MIN_SECRET_KEY_LENGTH


def test_validate_secret_key_placeholder_in_production_raises():
    """The built-in placeholder is rejected in a production environment."""
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_secret_key("production", secret_key=_SECRET_KEY_PLACEHOLDER)


def test_validate_secret_key_empty_in_production_raises():
    """An unset (empty) key is rejected in a production environment."""
    with pytest.raises(RuntimeError, match="unset or still uses"):
        validate_secret_key("production", secret_key="")


def test_validate_secret_key_short_in_production_raises():
    """A key shorter than the minimum length is rejected in production."""
    with pytest.raises(RuntimeError, match="too short"):
        validate_secret_key("production", secret_key="short-key")


def test_validate_secret_key_strong_in_production_passes():
    """A sufficiently long, non-placeholder key is accepted in production."""
    # Should not raise
    validate_secret_key("production", secret_key=_STRONG_KEY)


@pytest.mark.parametrize("environment", ["development", "dev", "local", "test", "testing", "TEST"])
def test_validate_secret_key_placeholder_allowed_in_dev_and_test(environment):
    """Dev and test environments may run on the placeholder (no extra config)."""
    # Should not raise even with the placeholder — matched case-insensitively
    validate_secret_key(environment, secret_key=_SECRET_KEY_PLACEHOLDER)
