"""Business logic for Product CRUD and photo upload.

Photo upload is handled via the upload_photo() helper which:
  - Enforces the 500 KB size limit (raises HTTP 413 if exceeded)
  - Uploads to Supabase Storage and returns the public URL
  - Called separately from create/update so the product route can accept
    a multipart form with a JSON body + file part
"""

import uuid

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    PRODUCT_CREATED,
    PRODUCT_DEACTIVATED,
    PRODUCT_PHOTO_UPDATED,
    PRODUCT_UPDATED,
)
from app.constants.statuses import ActorType
from app.models.category import Category
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.audit_service import log_action
from app.utils.storage import extension_for_content_type, upload_image

log = structlog.get_logger(__name__)

# Maximum photo size enforced before attempting Supabase upload
_MAX_PHOTO_BYTES = 500 * 1024  # 500 KB
_ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _get_or_404(db: AsyncSession, brand_id: uuid.UUID, product_id: uuid.UUID) -> Product:
    """
    Fetch a Product by ID scoped to a brand, or raise HTTP 404.

    Args:
        db: Active database session.
        brand_id: Brand scope — prevents cross-brand access.
        product_id: UUID of the product to fetch.

    Returns:
        Product: The found instance.

    Raises:
        HTTPException: 404 if not found within the brand.
    """
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.brand_id == brand_id,
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


async def _validate_category(
    db: AsyncSession, brand_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    """
    Raise HTTP 400 if the category does not belong to the given brand.

    Prevents assigning a product to a category from a different brand.

    Args:
        db: Active database session.
        brand_id: Expected brand owner of the category.
        category_id: UUID of the category to validate.

    Raises:
        HTTPException: 400 if the category belongs to a different brand.
        HTTPException: 404 if the category does not exist.
    """
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    cat = result.scalar_one_or_none()
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    if cat.brand_id != brand_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category belongs to a different brand",
        )


async def list_products(
    db: AsyncSession,
    brand_id: uuid.UUID,
    category_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Product]:
    """
    Return a paginated list of active products for a brand.

    Args:
        db: Active database session.
        brand_id: Scope to this brand.
        category_id: Optional filter — only products in this category.
        skip: Pagination offset.
        limit: Maximum rows to return.

    Returns:
        list[Product]: Active products ordered by display_order then name.
    """
    query = (
        select(Product)
        .where(Product.brand_id == brand_id, Product.is_active == True)  # noqa: E712
        .order_by(Product.display_order, Product.name)
        .offset(skip)
        .limit(limit)
    )
    if category_id is not None:
        query = query.where(Product.category_id == category_id)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product(
    db: AsyncSession, brand_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """
    Fetch a single product by ID, scoped to the brand.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to fetch.

    Returns:
        Product: The found product.

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, brand_id, product_id)


async def create_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    payload: ProductCreate,
    actor: User | SuperAdmin,
) -> Product:
    """
    Create a new product in the catalog and write an audit log row.

    Validates that the assigned category belongs to the same brand
    (cross-brand category assignment raises HTTP 400).

    Args:
        db: Active database session.
        brand_id: Brand to create the product under.
        payload: Product creation data.
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The newly created product.

    Raises:
        HTTPException: 400 if the category belongs to a different brand.
        HTTPException: 404 if the category does not exist.
    """
    await _validate_category(db, brand_id, payload.category_id)

    product = Product(
        id=uuid.uuid4(),
        brand_id=brand_id,
        category_id=payload.category_id,
        tax_category_id=payload.tax_category_id,
        name=payload.name,
        description=payload.description,
        base_price_cents=payload.base_price_cents,
        display_order=payload.display_order,
        is_active=True,
    )
    db.add(product)

    await log_action(
        db=db,
        action=PRODUCT_CREATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "name": product.name,
            "category_id": str(product.category_id),
            "base_price_cents": product.base_price_cents,
        },
    )

    await db.commit()
    await db.refresh(product)
    log.info("product.created", product_id=str(product.id), brand_id=str(brand_id))
    return product


async def update_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdate,
    actor: User | SuperAdmin,
) -> Product:
    """
    Update a product's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to update.
        payload: Fields to update (all optional).
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The updated product.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 400 if the new category belongs to a different brand.
    """
    product = await _get_or_404(db, brand_id, product_id)

    if payload.category_id is not None:
        await _validate_category(db, brand_id, payload.category_id)
        product.category_id = payload.category_id

    before = {"name": product.name, "base_price_cents": product.base_price_cents}

    if payload.tax_category_id is not None:
        product.tax_category_id = payload.tax_category_id
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.base_price_cents is not None:
        product.base_price_cents = payload.base_price_cents
    if payload.display_order is not None:
        product.display_order = payload.display_order

    await log_action(
        db=db,
        action=PRODUCT_UPDATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state={"name": product.name, "base_price_cents": product.base_price_cents},
    )

    await db.commit()
    await db.refresh(product)
    return product


async def deactivate_product(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    actor: User | SuperAdmin,
) -> Product:
    """
    Soft-delete a product by setting is_active=False.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to deactivate.
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The deactivated product.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if already inactive.
    """
    product = await _get_or_404(db, brand_id, product_id)

    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is already inactive",
        )

    product.is_active = False

    await log_action(
        db=db,
        action=PRODUCT_DEACTIVATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(product)
    return product


async def upload_photo(
    db: AsyncSession,
    brand_id: uuid.UUID,
    product_id: uuid.UUID,
    file: UploadFile,
    actor: User | SuperAdmin,
) -> Product:
    """
    Upload a product photo to Supabase Storage and save the URL on the product.

    Enforces a 500 KB limit before attempting the upload. Raises HTTP 413 if
    the file exceeds the limit. Raises HTTP 415 if the content type is not an
    accepted image type.

    Args:
        db: Active database session.
        brand_id: Brand scope.
        product_id: UUID of the product to attach the photo to.
        file: The uploaded image file (UploadFile from FastAPI).
        actor: The authenticated POS user performing the action.

    Returns:
        Product: The product with updated photo_url.

    Raises:
        HTTPException: 404 if the product is not found.
        HTTPException: 413 if the file exceeds 500 KB.
        HTTPException: 415 if the content type is not an accepted image type.
    """
    product = await _get_or_404(db, brand_id, product_id)

    contents = await file.read()
    ext = extension_for_content_type(file.content_type or "")
    photo_url = await upload_image(
        bucket="product-photos",
        path=f"products/{brand_id}/{product_id}.{ext}",
        content_type=file.content_type or "",
        contents=contents,
        allowed_content_types=_ALLOWED_PHOTO_TYPES,
        max_bytes=_MAX_PHOTO_BYTES,
    )

    old_url = product.photo_url
    product.photo_url = photo_url

    await log_action(
        db=db,
        action=PRODUCT_PHOTO_UPDATED,
        entity_type="product",
        entity_id=str(product.id),
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"photo_url": old_url},
        after_state={"photo_url": photo_url},
    )

    await db.commit()
    await db.refresh(product)
    log.info("product.photo.uploaded", product_id=str(product.id))
    return product
