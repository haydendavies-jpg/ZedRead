"""Unit tests for app/utils/storage.py.

Cover the process-wide Supabase client cache and the not-configured guard.
No database or real Supabase account is required — the SDK factory is patched.
"""

import pytest
from fastapi import HTTPException

import app.utils.storage as storage
from app.utils.storage import _get_storage_client, extension_for_content_type


@pytest.fixture(autouse=True)
def _reset_client_cache():
    """Reset the module-level client cache before and after each test."""
    storage._storage_client = None
    yield
    storage._storage_client = None


def test_get_storage_client_unconfigured_raises_503(monkeypatch):
    """_get_storage_client() raises 503 when Supabase env vars are unset."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_STORAGE_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        _get_storage_client()
    assert exc_info.value.status_code == 503


def test_get_storage_client_unconfigured_does_not_cache(monkeypatch):
    """A failed (unconfigured) build must not poison the cache."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_STORAGE_KEY", raising=False)

    with pytest.raises(HTTPException):
        _get_storage_client()
    assert storage._storage_client is None  # nothing cached on failure


def test_get_storage_client_builds_once_and_caches(monkeypatch):
    """The client is built a single time and reused on subsequent calls."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_STORAGE_KEY", "service-role-key")

    call_count = {"n": 0}
    sentinel = object()

    def _fake_create_client(url, key):
        call_count["n"] += 1
        return sentinel

    # Patch the SDK factory the module imports lazily
    import supabase

    monkeypatch.setattr(supabase, "create_client", _fake_create_client)

    first = _get_storage_client()
    second = _get_storage_client()

    assert first is sentinel
    assert second is first  # same cached instance
    assert call_count["n"] == 1  # built only once despite two calls


def test_extension_for_content_type_defaults_to_jpg():
    """extension_for_content_type() maps known types and defaults to jpg."""
    assert extension_for_content_type("image/png") == "png"
    assert extension_for_content_type("image/webp") == "webp"
    assert extension_for_content_type("application/octet-stream") == "jpg"
