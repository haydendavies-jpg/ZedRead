"""Integration tests for variant routes.

Five scenarios per tests_CLAUDE.md guidelines, covering happy paths,
error cases, and audit log assertions.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.product_attribute_type import ProductAttributeType
from app.models.product_attribute_value import ProductAttributeValue


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def attr_type(db: AsyncSession, test_brand) -> ProductAttributeType:
    """A persisted ProductAttributeType for test_brand."""
    at = ProductAttributeType(id=uuid.uuid4(), brand_id=test_brand.id, name="Size")
    db.add(at)
    await db.commit()
    await db.refresh(at)
    return at


@pytest_asyncio.fixture()
async def attr_value(db: AsyncSession, attr_type: ProductAttributeType) -> ProductAttributeValue:
    """A persisted ProductAttributeValue for attr_type."""
    av = ProductAttributeValue(
        id=uuid.uuid4(),
        attribute_type_id=attr_type.id,
        value="Large",
        display_order=0,
    )
    db.add(av)
    await db.commit()
    await db.refresh(av)
    return av


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_variant_happy_path(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """POST /products/{id}/variants returns 201 and the new variant."""
    resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {
                    "attribute_type_id": str(attr_type.id),
                    "attribute_value_id": str(attr_value.id),
                }
            ],
            "sku": "SKU-L",
            "price_cents": 1800,
        },
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sku"] == "SKU-L"
    assert data["price_cents"] == 1800
    assert data["is_active"] is True
    assert len(data["attributes"]) == 1


@pytest.mark.asyncio
async def test_create_variant_writes_audit_log(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
    db: AsyncSession,
) -> None:
    """Creating a variant writes a 'variant.created' audit log row."""
    await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {
                    "attribute_type_id": str(attr_type.id),
                    "attribute_value_id": str(attr_value.id),
                }
            ],
        },
        headers=pos_auth_headers,
    )
    result = await db.execute(select(AuditLog).where(AuditLog.action == "variant.created"))
    log = result.scalar_one_or_none()
    assert log is not None


@pytest.mark.asyncio
async def test_create_variant_duplicate_combination_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """Creating a variant with a duplicate attribute combination returns 409."""
    payload = {
        "attributes": [
            {
                "attribute_type_id": str(attr_type.id),
                "attribute_value_id": str(attr_value.id),
            }
        ]
    }
    # First creation succeeds
    r1 = await client.post(
        f"/products/{test_product.id}/variants", json=payload, headers=pos_auth_headers
    )
    assert r1.status_code == 201

    # Second creation with same combo should fail
    r2 = await client.post(
        f"/products/{test_product.id}/variants", json=payload, headers=pos_auth_headers
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_list_variants_returns_only_active(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """GET /products/{id}/variants returns only active variants."""
    # Create one variant then deactivate it
    av2 = ProductAttributeValue(
        id=uuid.uuid4(), attribute_type_id=attr_type.id, value="Small", display_order=1
    )

    # Create variant
    create_resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {
                    "attribute_type_id": str(attr_type.id),
                    "attribute_value_id": str(attr_value.id),
                }
            ]
        },
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    # Deactivate it
    del_resp = await client.delete(
        f"/products/{test_product.id}/variants/{variant_id}",
        headers=pos_auth_headers,
    )
    assert del_resp.status_code == 200

    # List should be empty
    list_resp = await client.get(
        f"/products/{test_product.id}/variants", headers=pos_auth_headers
    )
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_update_variant_price(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """PATCH /products/{id}/variants/{variant_id} updates price_cents."""
    create_resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {
                    "attribute_type_id": str(attr_type.id),
                    "attribute_value_id": str(attr_value.id),
                }
            ],
            "price_cents": 1000,
        },
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/products/{test_product.id}/variants/{variant_id}",
        json={"price_cents": 2500},
        headers=pos_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["price_cents"] == 2500


@pytest.mark.asyncio
async def test_deactivate_already_inactive_variant_returns_409(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """DELETEing an already inactive variant returns 409."""
    create_resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {
                    "attribute_type_id": str(attr_type.id),
                    "attribute_value_id": str(attr_value.id),
                }
            ]
        },
        headers=pos_auth_headers,
    )
    assert create_resp.status_code == 201
    variant_id = create_resp.json()["id"]

    # Deactivate once
    r1 = await client.delete(
        f"/products/{test_product.id}/variants/{variant_id}", headers=pos_auth_headers
    )
    assert r1.status_code == 200

    # Deactivate again → 409
    r2 = await client.delete(
        f"/products/{test_product.id}/variants/{variant_id}", headers=pos_auth_headers
    )
    assert r2.status_code == 409
