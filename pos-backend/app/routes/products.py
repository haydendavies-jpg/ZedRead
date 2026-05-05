"""Product catalog routes — scoped to the authenticated user's brand."""

import uuid

from fastapi import APIRouter, Depends, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from app.services import product_service
from app.utils.dependencies import POSAccess, resolve_access

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductResponse], status_code=status.HTTP_200_OK)
async def list_products(
    category_id: uuid.UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> list[ProductResponse]:
    """
    List active products for the authenticated user's brand.

    Optionally filter by category_id.

    Args:
        category_id: Optional category filter.
        skip: Pagination offset.
        limit: Maximum number of products to return.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        list[ProductResponse]: Active products ordered by display_order then name.
    """
    products = await product_service.list_products(
        db, access.user.brand_id, category_id, skip, limit
    )
    return [ProductResponse.model_validate(p) for p in products]


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Create a new product in the authenticated user's brand catalog.

    Args:
        payload: Product creation data.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ProductResponse: The created product.
    """
    product = await product_service.create_product(db, access.user.brand_id, payload, access.user)
    return ProductResponse.model_validate(product)


@router.get("/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def get_product(
    product_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Fetch a single product by ID.

    Args:
        product_id: UUID of the product to fetch.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ProductResponse: The product.
    """
    product = await product_service.get_product(db, access.user.brand_id, product_id)
    return ProductResponse.model_validate(product)


@router.patch("/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Update a product's mutable fields.

    Args:
        product_id: UUID of the product to update.
        payload: Fields to update.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ProductResponse: The updated product.
    """
    product = await product_service.update_product(
        db, access.user.brand_id, product_id, payload, access.user
    )
    return ProductResponse.model_validate(product)


@router.delete(
    "/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK
)
async def deactivate_product(
    product_id: uuid.UUID,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Soft-delete a product (set is_active=False).

    Args:
        product_id: UUID of the product to deactivate.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ProductResponse: The deactivated product.
    """
    product = await product_service.deactivate_product(
        db, access.user.brand_id, product_id, access.user
    )
    return ProductResponse.model_validate(product)


@router.post(
    "/{product_id}/photo",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_photo(
    product_id: uuid.UUID,
    file: UploadFile,
    access: POSAccess = Depends(resolve_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Upload or replace the product photo.

    Accepts JPEG, PNG, or WebP images up to 500 KB. Stores the image in
    Supabase Storage and saves the public URL on the product row.

    Args:
        product_id: UUID of the product to attach the photo to.
        file: The uploaded image file.
        access: Resolved POS access.
        db: Active database session.

    Returns:
        ProductResponse: The product with the updated photo_url.
    """
    product = await product_service.upload_photo(
        db, access.user.brand_id, product_id, file, access.user
    )
    return ProductResponse.model_validate(product)
