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


def _enabled() -> bool:
    """Return True unless RATE_LIMIT_ENABLED is explicitly set to 'false'."""
    # On by default (secure by default); opt out for load tests via the env var
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() != "false"


def reset() -> None:
    """Clear all recorded attempts. Used by tests to isolate state per case."""
    _hits.clear()


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

    now = time.monotonic()
    cutoff = now - window_seconds
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
