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


def test_stale_keys_are_evicted_by_periodic_sweep(monkeypatch):
    """Keys whose attempts have aged out of every window are dropped from memory."""
    # Record an attempt for a key, then age it out of its window
    fake_now = 1000.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_now)
    check_rate_limit("stale-key", max_attempts=3, window_seconds=60)
    assert "stale-key" in rate_limit._hits

    # Jump past the window and force the next call to run the sweep
    fake_now = 1000.0 + 61.0
    monkeypatch.setattr(rate_limit, "_calls_since_sweep", rate_limit._SWEEP_INTERVAL)
    check_rate_limit("fresh-key", max_attempts=3, window_seconds=60)

    # The aged-out key is gone; the active key remains
    assert "stale-key" not in rate_limit._hits
    assert "fresh-key" in rate_limit._hits


def test_sweep_does_not_drop_keys_still_inside_the_window(monkeypatch):
    """A key with an attempt still inside the window survives the sweep."""
    fake_now = 2000.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_now)
    check_rate_limit("recent-key", max_attempts=3, window_seconds=60)

    # Only 10 seconds pass — still inside the 60 s window when the sweep runs
    fake_now = 2000.0 + 10.0
    monkeypatch.setattr(rate_limit, "_calls_since_sweep", rate_limit._SWEEP_INTERVAL)
    check_rate_limit("other-key", max_attempts=3, window_seconds=60)

    assert "recent-key" in rate_limit._hits
