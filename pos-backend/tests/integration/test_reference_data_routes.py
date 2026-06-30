"""Integration tests for /reference routes.

Covers:
1. Happy path — timezones/countries/currencies/tax-id-label return correct shapes
2. Auth failure — no token → 403
3. Invalid input — missing/invalid country query param → 422
"""

import pytest

pytestmark = pytest.mark.asyncio


# ── Happy path ────────────────────────────────────────────────────────────────


async def test_get_timezones_returns_200(client, portal_auth_headers):
    """GET /reference/timezones returns a non-empty, sorted list of IANA zone names."""
    response = await client.get("/reference/timezones", headers=portal_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert "Australia/Sydney" in body
    assert body == sorted(body)


async def test_get_countries_returns_200(client, portal_auth_headers):
    """GET /reference/countries returns a list of {code, name} entries including Australia."""
    response = await client.get("/reference/countries", headers=portal_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    codes = {c["code"] for c in body}
    assert "AU" in codes
    au = next(c for c in body if c["code"] == "AU")
    assert au["name"] == "Australia"


async def test_get_currencies_returns_200(client, portal_auth_headers):
    """GET /reference/currencies returns a list of {code, name} entries including AUD."""
    response = await client.get("/reference/currencies", headers=portal_auth_headers)

    assert response.status_code == 200
    body = response.json()
    codes = {c["code"] for c in body}
    assert "AUD" in codes


async def test_get_tax_id_label_for_mapped_country(client, portal_auth_headers):
    """GET /reference/tax-id-label?country=AU returns 'ABN'."""
    response = await client.get(
        "/reference/tax-id-label", params={"country": "AU"}, headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["label"] == "ABN"


async def test_get_tax_id_label_for_unmapped_country_falls_back(client, portal_auth_headers):
    """GET /reference/tax-id-label?country=ZZ returns the default 'Tax ID' label."""
    response = await client.get(
        "/reference/tax-id-label", params={"country": "ZZ"}, headers=portal_auth_headers
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Tax ID"


# ── Auth failure ──────────────────────────────────────────────────────────────


async def test_get_timezones_no_token_returns_403(client):
    """GET /reference/timezones without a token returns 403."""
    response = await client.get("/reference/timezones")
    assert response.status_code == 403


async def test_get_countries_no_token_returns_403(client):
    """GET /reference/countries without a token returns 403."""
    response = await client.get("/reference/countries")
    assert response.status_code == 403


# ── Invalid input ─────────────────────────────────────────────────────────────


async def test_get_tax_id_label_missing_country_returns_422(client, portal_auth_headers):
    """GET /reference/tax-id-label with no country query param returns 422."""
    response = await client.get("/reference/tax-id-label", headers=portal_auth_headers)
    assert response.status_code == 422


async def test_get_tax_id_label_wrong_length_country_returns_422(client, portal_auth_headers):
    """GET /reference/tax-id-label with a non-2-letter country code returns 422."""
    response = await client.get(
        "/reference/tax-id-label", params={"country": "AUS"}, headers=portal_auth_headers
    )
    assert response.status_code == 422
