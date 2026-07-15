"""In-process rate limiter for authentication endpoints (brute-force mitigation).

Keeps a sliding window of recent attempt timestamps per key in memory. Keys are
normally an account identifier (email) so a brute-force attempt against one
account is throttled regardless of source IP — which matters here because the
app runs behind a proxy where per-IP limiting would see a single shared address.

This is deliberately single-process: it protects each API instance without a
Redis round trip. A distributed, shared-store limiter can replace it later
without changing call sites (see check_rate_limit's signature).
"""

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

# Per-key deque of monotonic attempt timestamps (oldest first)
_hits: dict[str, deque[float]] = defaultdict(deque)

# Sweep stale keys once per this many check_rate_limit calls. Without eviction
# the dict keeps one entry per key ever attempted (e.g. a bot cycling fake
# emails), growing without bound over the process lifetime.
_SWEEP_INTERVAL: int = 1024

# Calls since the last sweep, and the largest window ever requested — any
# bucket whose newest timestamp is older than that window is dead for every
# possible limit and can be dropped safely.
_calls_since_sweep: int = 0
_max_window_seconds: float = 0.0


def _sweep_stale_keys(now: float) -> None:
    """
    Drop buckets whose newest attempt has aged out of every possible window.

    Args:
        now: Current monotonic timestamp.

    Returns:
        None
    """
    cutoff = now - _max_window_seconds
    # Materialise the key list — deleting while iterating a dict raises
    stale = [key for key, bucket in _hits.items() if not bucket or bucket[-1] < cutoff]
    for key in stale:
        del _hits[key]


def _enabled() -> bool:
    """Return True unless RATE_LIMIT_ENABLED is explicitly set to 'false'."""
    # On by default (secure by default); opt out for load tests via the env var
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() != "false"


def reset() -> None:
    """Clear all recorded attempts and sweep state. Used by tests to isolate state per case."""
    global _calls_since_sweep, _max_window_seconds
    _hits.clear()
    _calls_since_sweep = 0
    _max_window_seconds = 0.0


def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """
    Record an attempt for ``key`` and raise 429 if it exceeds the window budget.

    Args:
        key: Identifier for the throttle bucket (e.g. ``"pos_login:user@x.com"``).
        max_attempts: Maximum attempts permitted within the window.
        window_seconds: Length of the sliding window in seconds.

    Raises:
        HTTPException: 429 (with a Retry-After header) if the budget is exceeded.
            The current attempt is not recorded when it is rejected.
    """
    if not _enabled():
        return

    global _calls_since_sweep, _max_window_seconds

    now = time.monotonic()
    cutoff = now - window_seconds

    # Periodically evict keys whose attempts have all aged out — otherwise the
    # dict grows by one entry per distinct key forever (slow memory leak)
    _max_window_seconds = max(_max_window_seconds, float(window_seconds))
    _calls_since_sweep += 1
    if _calls_since_sweep >= _SWEEP_INTERVAL:
        _calls_since_sweep = 0
        _sweep_stale_keys(now)

    bucket = _hits[key]

    # Drop timestamps that have aged out of the window
    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= max_attempts:
        # Seconds until the oldest in-window attempt expires and frees a slot
        retry_after = int(window_seconds - (now - bucket[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
