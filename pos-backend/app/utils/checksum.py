"""SHA-256 checksum helpers for offline-sync integrity verification (Android POS Phase 2).

Invoices and register sessions each carry a checksum over a canonical JSON
serialization of their sync-relevant fields, computed on-device and
re-verified here against whatever the server itself would compute from the
same data — a mismatch means the payload was altered or corrupted in
transit and is rejected outright rather than silently accepted.
"""

import hashlib
import json
from typing import Any

from fastapi import HTTPException, status


def canonical_json(data: dict[str, Any]) -> str:
    """
    Serialize a dict to a canonical JSON string — sorted keys, no whitespace.

    Args:
        data: The data to serialize. Must already be JSON-primitive (str,
            int, bool, None, list, dict) — callers must stringify UUID/
            Decimal/datetime values before calling this.

    Returns:
        str: Canonical JSON representation, stable for the same logical data
            regardless of dict insertion order.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: dict[str, Any]) -> str:
    """
    Compute the SHA-256 checksum of a dict's canonical JSON serialization.

    Args:
        data: The data to checksum.

    Returns:
        str: 64-character lowercase hex digest.
    """
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def verify_checksum(data: dict[str, Any], client_checksum: str | None) -> str:
    """
    Compute a dict's canonical checksum and verify it against a client-supplied value.

    Always computes and returns the server's own checksum — even when
    client_checksum is None — so callers can store/echo it back to the
    device once it starts sending one.

    Args:
        data: The data to checksum.
        client_checksum: The checksum the client claims for this data, or
            None if the client did not supply one (verification is skipped).

    Returns:
        str: The server-computed checksum.

    Raises:
        HTTPException: 422 if client_checksum is supplied and does not match.
    """
    server_checksum = sha256_hex(data)
    if client_checksum is not None and client_checksum != server_checksum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Checksum verification failed — data may have been corrupted in transit",
        )
    return server_checksum
