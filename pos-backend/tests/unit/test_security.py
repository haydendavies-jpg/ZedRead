"""Unit tests for app/utils/security.py.

Tests cover password hashing (argon2) and JWT token creation/validation.
No database is required — these are pure function tests.
"""

import pytest
from jose import JWTError

from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
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
