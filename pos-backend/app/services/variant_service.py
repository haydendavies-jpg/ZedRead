"""Business logic for product variants, attribute types, and attribute values.

Duplicate-combination guard: before inserting a new variant, the service checks
that no existing active variant for the same product has the identical set of
(attribute_type_id, attribute_value_id) pairs. A 409 is returned if one exists.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    VARIANT_CREATED,
    VARIANT_DEACTIVATED,
    VARIANT_REACTIVATED,
    VARIANT_UPDATED,
)
from app.constants.statuses import ActorType
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.product import Product
from app.models.product_attribute_type import ProductAttributeType
from app.models.product_attribute_value import ProductAttributeValue
from app.models.product_variant import ProductVariant
from app.models.product_variant_attribute import ProductVariantAttribute
from app.schemas.variant import (
    AttributeAssignment,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_product_or_404(
    db: AsyncSession, brand_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """
    Fetch a Product scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product.

    Returns:
        Product: The found instance.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.brand_id == brand_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


async def _get_variant_or_404(
    db: AsyncSession, brand_id: uuid.UUID, variant_id: uuid.UUID
) -> ProductVariant:
    """
    Fetch a ProductVariant scoped to a brand via its parent product.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        variant_id: UUID of the variant.

    Returns:
        ProductVariant: The found instance.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(ProductVariant)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(ProductVariant.id == variant_id, Product.brand_id == brand_id)
    )
    variant = result.scalar_one_or_none()
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


async def _load_attributes(
    db: AsyncSession, variant_id: uuid.UUID
) -> list[AttributeAssignment]:
    """Return the attribute assignments for a variant as AttributeAssignment objects."""
    result = await db.execute(
        select(ProductVariantAttribute).where(ProductVariantAttribute.variant_id == variant_id)
    )
    return [
        AttributeAssignment(
            attribute_type_id=row.attribute_type_id,
            attribute_value_id=row.attribute_value_id,
        )
        for row in result.scalars().all()
    ]


async def _check_duplicate_combination(
    db: AsyncSession,
    product_id: uuid.UUID,
    attributes: list[AttributeAssignment],
    exclude_variant_id: uuid.UUID | None = None,
) -> None:
    """
    Raise HTTP 409 if an existing active variant has the identical attribute combination.

    The check normalises the input list to a frozenset of (type_id, value_id) tuples
    and compares against all active variants for the same product.

    Args:
        db: Active database session.
        product_id: Product to check variants for.
        attributes: The proposed attribute assignments.
        exclude_variant_id: Skip this variant (used when updating).

    Raises:
        HTTPException: 409 if a duplicate combination already exists.
    """
    proposed = frozenset(
        (str(a.attribute_type_id), str(a.attribute_value_id)) for a in attributes
    )

    # Load all active variants for this product
    variants_result = await db.execute(
        select(ProductVariant).where(
            ProductVariant.product_id == product_id,
            ProductVariant.is_active == True,  # noqa: E712
        )
    )
    existing_variants = variants_result.scalars().all()

    for variant in existing_variants:
        if exclude_variant_id and variant.id == exclude_variant_id:
            continue

        attrs_result = await db.execute(
            select(ProductVariantAttribute).where(
                ProductVariantAttribute.variant_id == variant.id
            )
        )
        existing_combo = frozenset(
            (str(a.attribute_type_id), str(a.attribute_value_id))
            for a in attrs_result.scalars().all()
        )

        if existing_combo == proposed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A variant with this exact attribute combination already exists",
            )


# ── Public service functions ───────────────────────────────────────────────────


async def variant_to_response(db: AsyncSession, variant: ProductVariant) -> VariantResponse:
    """Assemble a VariantResponse for a variant, loading its attribute assignments."""
    attrs = await _load_attributes(db, variant.id)
    return VariantResponse(
        id=variant.id,
        ref=variant.ref,
        product_id=variant.product_id,
        sku=variant.sku,
        price_cents=variant.price_cents,
        display_name=variant.display_name,
        is_active=variant.is_active,
        attributes=attrs,
    )


async def list_variants(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
) -> list[VariantResponse]:
    """
    Return active variants for a product with their attribute assignments.

    Args:
        db: Active database session.
        brand_id: Brand scope — validates the product belongs to this brand.
        product_id: Product to list variants for.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[VariantResponse]: Active variants with attribute data.

    Raises:
        HTTPException: 404 if the product is not found within the brand.
    """
    await _get_product_or_404(db, brand_id, product_id)

    result = await db.execute(
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.is_active == True,  # noqa: E712
        )
        .offset(skip)
        .limit(limit)
    )
    variants = result.scalars().all()
    return [await variant_to_response(db, v) for v in variants]


async def list_variants_for_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 200,
) -> list[tuple[ProductVariant, str, str]]:
    """
    Return every variant across the brand's catalog, joined to its parent product.

    Powers the Stage 22 combined Variants+Combos portal page, which lists
    variants across all products rather than one product at a time.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Optional filter — only variants of this product.
        include_inactive: When True, also return soft-deleted variants.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[tuple[ProductVariant, str, str]]: Each tuple is
            (variant, product_name, product_ref), ordered by product name.
    """
    query = (
        select(ProductVariant, Product.name, Product.ref)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(Product.brand_id == brand_id)
        .order_by(Product.name, ProductVariant.created_at)
        .offset(skip)
        .limit(limit)
    )
    if not include_inactive:
        query = query.where(ProductVariant.is_active == True)  # noqa: E712
    if product_id is not None:
        query = query.where(ProductVariant.product_id == product_id)

    result = await db.execute(query)
    return [tuple(row) for row in result.all()]


async def create_variant(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: VariantCreate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> VariantResponse:
    """
    Create a product variant and its attribute assignments.

    Validates that all attribute types and values belong to the same brand.
    Checks for duplicate attribute combinations (returns 409 if found).

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: Product to add the variant to.
        payload: Variant data including attribute assignments.
        actor: The authenticated POS user performing the action.

    Returns:
        VariantResponse: The newly created variant with attributes.

    Raises:
        HTTPException: 404 if product, attribute type, or value not found.
        HTTPException: 409 if the attribute combination already exists.
    """
    await _get_product_or_404(db, brand_id, product_id)

    # Validate all attribute types belong to this brand
    for assignment in payload.attributes:
        type_result = await db.execute(
            select(ProductAttributeType).where(
                ProductAttributeType.id == assignment.attribute_type_id,
                ProductAttributeType.brand_id == brand_id,
            )
        )
        if type_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attribute type {assignment.attribute_type_id} not found in this brand",
            )

        val_result = await db.execute(
            select(ProductAttributeValue).where(
                ProductAttributeValue.id == assignment.attribute_value_id,
                ProductAttributeValue.attribute_type_id == assignment.attribute_type_id,
            )
        )
        if val_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attribute value {assignment.attribute_value_id} not found for that type",
            )

    await _check_duplicate_combination(db, product_id, payload.attributes)

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product_id,
        sku=payload.sku,
        price_cents=payload.price_cents,
        display_name=payload.display_name,
        is_active=True,
    )
    db.add(variant)
    await db.flush()  # Need variant.id before inserting attributes

    for assignment in payload.attributes:
        db.add(
            ProductVariantAttribute(
                variant_id=variant.id,
                attribute_type_id=assignment.attribute_type_id,
                attribute_value_id=assignment.attribute_value_id,
            )
        )

    after_state: dict = {
        "product_id": str(product_id),
        "price_cents": payload.price_cents,
        "attribute_count": len(payload.attributes),
    }
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=VARIANT_CREATED,
        entity_type="product_variant",
        entity_id=str(variant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state=after_state,
    )

    await db.commit()
    log.info("variant.created", variant_id=str(variant.id), product_id=str(product_id))
    return await variant_to_response(db, variant)


async def update_variant(
    db: AsyncSession,
    brand_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> VariantResponse:
    """
    Update a variant's price, SKU, or display name. Attributes are immutable after creation.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        variant_id: UUID of the variant to update.
        payload: Fields to update.
        actor: The authenticated POS user.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

    Returns:
        VariantResponse: The updated variant.

    Raises:
        HTTPException: 404 if not found.
    """
    variant = await _get_variant_or_404(db, brand_id, variant_id)
    before = {"price_cents": variant.price_cents, "sku": variant.sku, "display_name": variant.display_name}

    if payload.sku is not None:
        variant.sku = payload.sku
    if payload.price_cents is not None:
        variant.price_cents = payload.price_cents
    if payload.display_name is not None:
        variant.display_name = payload.display_name

    after_state = {"price_cents": variant.price_cents, "sku": variant.sku, "display_name": variant.display_name}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=VARIANT_UPDATED,
        entity_type="product_variant",
        entity_id=str(variant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after_state,
    )

    await db.commit()
    return await variant_to_response(db, variant)


async def deactivate_variant(
    db: AsyncSession,
    brand_id: uuid.UUID,
    variant_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> VariantResponse:
    """
    Soft-delete a variant (set is_active=False).

    Args:
        db: Active database session.
        brand_id: Brand scope.
        variant_id: UUID of the variant to deactivate.
        actor: The authenticated POS user.

    Returns:
        VariantResponse: The deactivated variant.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if already inactive.
    """
    variant = await _get_variant_or_404(db, brand_id, variant_id)

    if not variant.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variant is already inactive",
        )

    variant.is_active = False

    await log_action(
        db=db,
        action=VARIANT_DEACTIVATED,
        entity_type="product_variant",
        entity_id=str(variant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    return await variant_to_response(db, variant)


async def set_variant_active_state(
    db: AsyncSession,
    brand_id: uuid.UUID,
    variant_id: uuid.UUID,
    is_active: bool,
    actor: User | SuperAdmin,
    import_id: uuid.UUID | None = None,
) -> VariantResponse:
    """
    Set a variant's is_active flag directly (activate or soft-delete), idempotently.

    Unlike deactivate_variant(), setting the flag to its current value is a
    silent no-op rather than a 409 — same convention as
    product_service.set_product_active_state(), used by import_service.py and
    the portal's POST /products/{id}/variants/{id}/activate route.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        variant_id: UUID of the variant to update.
        is_active: The desired active state.
        actor: The authenticated user performing the action.
        import_id: Batch ID shared by every row of a bulk import; None for direct calls.

    Returns:
        VariantResponse: The variant, with is_active set to the requested value.

    Raises:
        HTTPException: 404 if not found.
    """
    variant = await _get_variant_or_404(db, brand_id, variant_id)
    if variant.is_active == is_active:
        return await variant_to_response(db, variant)

    variant.is_active = is_active

    after_state: dict = {"is_active": is_active}
    if import_id is not None:
        after_state["import_id"] = str(import_id)

    await log_action(
        db=db,
        action=VARIANT_REACTIVATED if is_active else VARIANT_DEACTIVATED,
        entity_type="product_variant",
        entity_id=str(variant.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": not is_active},
        after_state=after_state,
    )

    await db.commit()
    return await variant_to_response(db, variant)
