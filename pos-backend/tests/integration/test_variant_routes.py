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


# ── Stage 22 — ref, display_name, brand-wide list/export/import ──────────────


@pytest.mark.asyncio
async def test_create_variant_has_ref_and_display_name(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """A newly created variant carries a VAR-000001-style ref and honours display_name."""
    resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {"attribute_type_id": str(attr_type.id), "attribute_value_id": str(attr_value.id)}
            ],
            "display_name": "Large Spicy",
        },
        headers=pos_auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ref"].startswith("VAR-")
    assert data["display_name"] == "Large Spicy"


@pytest.mark.asyncio
async def test_activate_variant_is_idempotent(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
    db: AsyncSession,
) -> None:
    """POST .../activate reactivates a deactivated variant and writes 'variant.reactivated'; a repeat call is a no-op."""
    create_resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {"attribute_type_id": str(attr_type.id), "attribute_value_id": str(attr_value.id)}
            ]
        },
        headers=pos_auth_headers,
    )
    variant_id = create_resp.json()["id"]

    await client.delete(f"/products/{test_product.id}/variants/{variant_id}", headers=pos_auth_headers)

    r1 = await client.post(
        f"/products/{test_product.id}/variants/{variant_id}/activate", headers=pos_auth_headers
    )
    assert r1.status_code == 200
    assert r1.json()["is_active"] is True

    # Idempotent — second call is a no-op, no error
    r2 = await client.post(
        f"/products/{test_product.id}/variants/{variant_id}/activate", headers=pos_auth_headers
    )
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True

    result = await db.execute(select(AuditLog).where(AuditLog.action == "variant.reactivated"))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_list_brand_variants_includes_linked_product(
    client: AsyncClient,
    pos_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
) -> None:
    """GET /variants lists variants across the brand joined to their parent product."""
    await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {"attribute_type_id": str(attr_type.id), "attribute_value_id": str(attr_value.id)}
            ]
        },
        headers=pos_auth_headers,
    )

    resp = await client.get("/variants", headers=pos_auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["product_id"] == str(test_product.id)
    assert data[0]["product_name"] == test_product.name
    assert data[0]["product_ref"] == test_product.ref


@pytest.mark.asyncio
async def test_import_variants_requires_ref(
    client: AsyncClient,
    mgmt_auth_headers: dict,
) -> None:
    """A variant import row with a blank ref is reported as an error, not created."""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["ref", "display_name"])
    ws.append(["", "Should not be created"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = await client.post(
        "/variants/import",
        files={"file": ("variants.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=mgmt_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 0
    assert data["updated"] == 0
    assert len(data["errors"]) == 1


@pytest.mark.asyncio
async def test_import_variants_updates_by_ref(
    client: AsyncClient,
    mgmt_auth_headers: dict,
    test_product,
    attr_type: ProductAttributeType,
    attr_value: ProductAttributeValue,
    db: AsyncSession,
) -> None:
    """A variant import row with a known ref updates display_name and writes an audit row with import_id."""
    import io

    from openpyxl import Workbook

    create_resp = await client.post(
        f"/products/{test_product.id}/variants",
        json={
            "attributes": [
                {"attribute_type_id": str(attr_type.id), "attribute_value_id": str(attr_value.id)}
            ]
        },
        headers=mgmt_auth_headers,
    )
    ref = create_resp.json()["ref"]

    wb = Workbook()
    ws = wb.active
    ws.append(["ref", "display_name"])
    ws.append([ref, "Renamed via import"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = await client.post(
        "/variants/import",
        files={"file": ("variants.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=mgmt_auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == 1
    assert data["errors"] == []

    result = await db.execute(select(AuditLog).where(AuditLog.action == "variant.updated"))
    log = result.scalar_one()
    assert log.after_state["import_id"] == data["import_id"]
