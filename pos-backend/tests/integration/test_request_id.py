"""Integration test verifying that every response includes a valid X-Request-ID header.

This is the first integration test in the project — it confirms that the
RequestLoggingMiddleware is correctly wired into the FastAPI app and that the
UUID is a valid format (not just any string).
"""

import re
import uuid

import pytest

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


async def test_health_check_returns_200(client):
    """GET /health returns 200 with the expected payload."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_every_response_has_x_request_id_header(client):
    """Every API response carries an X-Request-ID header set by RequestLoggingMiddleware."""
    response = await client.get("/health")

    assert "x-request-id" in response.headers, (
        "X-Request-ID header is missing — RequestLoggingMiddleware may not be wired up"
    )


async def test_x_request_id_is_a_valid_uuid(client):
    """The X-Request-ID value must be a well-formed UUID v4."""
    response = await client.get("/health")

    header_value = response.headers.get("x-request-id", "")

    # Validate UUID v4 format — must not be empty, random, or malformed
    assert UUID_PATTERN.match(header_value), (
        f"X-Request-ID '{header_value}' is not a valid UUID v4"
    )


async def test_every_response_has_x_response_time_ms_header(client):
    """Every API response carries a non-negative integer X-Response-Time-Ms header."""
    response = await client.get("/health")

    header_value = response.headers.get("x-response-time-ms")
    assert header_value is not None, (
        "X-Response-Time-Ms header is missing — duration timing may not be wired up"
    )
    # Must parse as a non-negative integer number of milliseconds
    assert header_value.isdigit(), (
        f"X-Response-Time-Ms '{header_value}' is not a non-negative integer"
    )


async def test_each_request_gets_a_unique_request_id(client):
    """Two requests to the same endpoint must receive different request IDs."""
    response_a = await client.get("/health")
    response_b = await client.get("/health")

    id_a = response_a.headers.get("x-request-id")
    id_b = response_b.headers.get("x-request-id")

    assert id_a != id_b, "Two requests received the same X-Request-ID — IDs are not unique"
