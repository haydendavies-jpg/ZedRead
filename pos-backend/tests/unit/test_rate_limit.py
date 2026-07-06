"""Unit tests for app/utils/rate_limit.py."""

import pytest
from fastapi import HTTPException

from app.utils import rate_limit
from app.utils.rate_limit import check_rate_limit


@pytest.fixture(autouse=True)
def _clear():
    """Isolate limiter state per test."""
    rate_limit.reset()
    yield
    rate_limit.reset()


def test_allows_up_to_the_limit():
    """The first max_attempts calls are allowed."""
    for _ in range(3):
        check_rate_limit("k", max_attempts=3, window_seconds=60)  # no raise


def test_blocks_over_the_limit():
    """The call that exceeds max_attempts raises 429 with Retry-After."""
    for _ in range(3):
        check_rate_limit("k", max_attempts=3, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit("k", max_attempts=3, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_keys_are_independent():
    """Exhausting one key does not affect another."""
    for _ in range(3):
        check_rate_limit("a", max_attempts=3, window_seconds=60)
    # Different key still has its full budget
    check_rate_limit("b", max_attempts=3, window_seconds=60)  # no raise


def test_disabled_via_env(monkeypatch):
    """RATE_LIMIT_ENABLED=false makes the limiter a no-op."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    for _ in range(100):
        check_rate_limit("k", max_attempts=1, window_seconds=60)  # never raises
