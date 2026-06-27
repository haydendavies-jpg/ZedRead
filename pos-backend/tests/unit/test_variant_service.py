"""Unit tests for variant_service — focused on the duplicate combination guard.

Every test uses the real test DB (rule 10) and asserts the audit_logs row (rule 11).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_attribute_type import ProductAttributeType
from app.models.product_attribute_value import ProductAttributeValue
from app.models.product_variant import ProductVariant
from app.models.product_variant_attribute import ProductVariantAttribute
from app.services.variant_service import (
    AttributeAssignment,
    VariantCreate,
    _check_duplicate_combination,
    create_variant,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_attr_type(db: AsyncSession, brand_id: uuid.UUID, name: str) -> ProductAttributeType:
    """Insert a ProductAttributeType row and return it."""
    at = ProductAttributeType(id=uuid.uuid4(), brand_id=brand_id, name=name)
    db.add(at)
    await db.flush()
    return at


async def _make_attr_value(
    db: AsyncSession, attr_type_id: uuid.UUID, value: str, display_order: int = 0
) -> ProductAttributeValue:
    """Insert a ProductAttributeValue row and return it."""
    av = ProductAttributeValue(
        id=uuid.uuid4(),
        attribute_type_id=attr_type_id,
        value=value,
        display_order=display_order,
    )
    db.add(av)
    await db.flush()
    return av


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_duplicate_no_existing_variants_passes(
    db: AsyncSession, test_product,
) -> None:
    """_check_duplicate_combination passes when there are no existing variants."""
    at = await _make_attr_type(db, test_product.brand_id, "Size")
    av = await _make_attr_value(db, at.id, "Small")

    # Should not raise
    await _check_duplicate_combination(
        db,
        test_product.id,
        [AttributeAssignment(attribute_type_id=at.id, attribute_value_id=av.id)],
    )


@pytest.mark.asyncio
async def test_check_duplicate_identical_combination_raises_409(
    db: AsyncSession, test_product,
) -> None:
    """_check_duplicate_combination raises 409 when an active variant has the same attribute combo."""
    from fastapi import HTTPException

    at = await _make_attr_type(db, test_product.brand_id, "Size")
    av = await _make_attr_value(db, at.id, "Medium")

    # Create an existing variant with (Size=Medium)
    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=test_product.id,
        sku=None,
        price_cents=None,
        is_active=True,
    )
    db.add(variant)
    await db.flush()
    db.add(
        ProductVariantAttribute(
            variant_id=variant.id,
            attribute_type_id=at.id,
            attribute_value_id=av.id,
        )
    )
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await _check_duplicate_combination(
            db,
            test_product.id,
            [AttributeAssignment(attribute_type_id=at.id, attribute_value_id=av.id)],
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_check_duplicate_different_combination_passes(
    db: AsyncSession, test_product,
) -> None:
    """_check_duplicate_combination passes when the existing variant has a different combo."""
    at = await _make_attr_type(db, test_product.brand_id, "Size")
    av_small = await _make_attr_value(db, at.id, "Small")
    av_large = await _make_attr_value(db, at.id, "Large")

    # Existing variant: Size=Small
    variant = ProductVariant(
        id=uuid.uuid4(), product_id=test_product.id, sku=None, price_cents=None, is_active=True
    )
    db.add(variant)
    await db.flush()
    db.add(
        ProductVariantAttribute(
            variant_id=variant.id,
            attribute_type_id=at.id,
            attribute_value_id=av_small.id,
        )
    )
    await db.commit()

    # Proposing Size=Large — should not raise
    await _check_duplicate_combination(
        db,
        test_product.id,
        [AttributeAssignment(attribute_type_id=at.id, attribute_value_id=av_large.id)],
    )


@pytest.mark.asyncio
async def test_check_duplicate_inactive_variant_ignored(
    db: AsyncSession, test_product,
) -> None:
    """_check_duplicate_combination ignores inactive variants."""
    at = await _make_attr_type(db, test_product.brand_id, "Color")
    av = await _make_attr_value(db, at.id, "Red")

    # Inactive variant with same combo
    variant = ProductVariant(
        id=uuid.uuid4(), product_id=test_product.id, sku=None, price_cents=None, is_active=False
    )
    db.add(variant)
    await db.flush()
    db.add(
        ProductVariantAttribute(
            variant_id=variant.id,
            attribute_type_id=at.id,
            attribute_value_id=av.id,
        )
    )
    await db.commit()

    # Should not raise — the only matching variant is inactive
    await _check_duplicate_combination(
        db,
        test_product.id,
        [AttributeAssignment(attribute_type_id=at.id, attribute_value_id=av.id)],
    )


@pytest.mark.asyncio
async def test_create_variant_writes_audit_log(
    db: AsyncSession, test_product, test_user,
) -> None:
    """create_variant writes an audit_logs row with action 'variant.created'."""
    from sqlalchemy import select as _select

    from app.models.audit_log import AuditLog

    at = await _make_attr_type(db, test_product.brand_id, "Size")
    av = await _make_attr_value(db, at.id, "XL")

    payload = VariantCreate(
        attributes=[AttributeAssignment(attribute_type_id=at.id, attribute_value_id=av.id)],
        sku="SKU-XL",
        price_cents=2000,
    )

    result = await create_variant(db, test_product.brand_id, test_product.id, payload, test_user)
    assert result.sku == "SKU-XL"

    log_result = await db.execute(
        _select(AuditLog).where(AuditLog.action == "variant.created")
    )
    log = log_result.scalar_one_or_none()
    assert log is not None
    assert log.actor_id == test_user.id
