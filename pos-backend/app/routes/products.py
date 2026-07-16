"""Product catalog routes — scoped to the authenticated user's brand."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.import_export import ImportSummary
from app.schemas.product import (
    ProductBulkUpdate,
    ProductBulkUpdateResult,
    ProductCreate,
    ProductListItem,
    ProductResponse,
    ProductUpdate,
)
from app.services import export_service, import_service, product_service
from app.services.import_service import InvalidWorkbookError
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/products", tags=["products"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_model=list[ProductListItem], status_code=status.HTTP_200_OK)
async def list_products(
    category_id: uuid.UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    include_inactive: bool = Query(False, description="Include soft-deleted products (Stage 20 table view)"),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ProductListItem]:
    """
    List products for the authenticated user's brand, joined to Category and Reporting Group.

    Optionally filter by category_id. Excludes soft-deleted products unless
    include_inactive is set.

    Args:
        category_id: Optional category filter.
        skip: Pagination offset.
        limit: Maximum number of products to return.
        include_inactive: Include soft-deleted products.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ProductListItem]: Products ordered by display_order then name, each
            carrying its joined category_name/category_color, reporting_group_id,
            reporting_group_name, and comma-joined modifier_names.
    """
    rows = await product_service.list_products(
        db, access.effective_brand_id(brand_id), category_id, skip, limit, include_inactive
    )
    return [
        ProductListItem(
            **ProductResponse.model_validate(product).model_dump(),
            category_name=category_name,
            category_color=category_color,
            reporting_group_id=reporting_group_id,
            reporting_group_name=reporting_group_name,
            modifier_names=modifier_names,
        )
        for product, category_name, category_color, reporting_group_id, reporting_group_name, modifier_names in rows
    ]


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Create a new product in the authenticated user's brand catalog.

    Args:
        payload: Product creation data.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The created product.
    """
    product = await product_service.create_product(db, access.effective_brand_id(brand_id), payload, access.actor_user)
    return ProductResponse.model_validate(product)


@router.post("/bulk", response_model=ProductBulkUpdateResult, status_code=status.HTTP_200_OK)
async def bulk_update_products(
    payload: ProductBulkUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductBulkUpdateResult:
    """
    Apply one or more field changes to a set of products in one call.

    All-or-nothing: if any product_id (or a reassigned category_id/
    tax_category_id/modifier_group_id) does not belong to this brand, the
    whole batch is rejected with HTTP 400 before any row is touched. Setting
    is_active=False is the bulk archive action — it cascades, deleting the
    archived products' modifier links and any menu_buttons pointing at them;
    see product_service.bulk_update_products for the full field contract.

    Args:
        payload: The bulk update fields to apply.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductBulkUpdateResult: Count and ids of the products actually modified.
    """
    return await product_service.bulk_update_products(
        db, access.effective_brand_id(brand_id), payload, access.actor_user
    )


@router.get("/export/template", response_model=None, status_code=status.HTTP_200_OK)
async def export_products_template(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download a blank Products import template (header row + example + category dropdown).

    response_model is intentionally omitted — the body is a binary .xlsx file,
    not a JSON payload a Pydantic model could describe (CLAUDE.md rule 12 is
    about typed JSON responses; a streamed spreadsheet has no such schema).

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx template file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_products_template(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=products_template.xlsx"},
    )


@router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_products(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the brand's current Products catalog as a re-importable .xlsx file.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_products_export(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=products_export.xlsx"},
    )


@router.post("/import", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_products(
    file: UploadFile,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """
    Bulk create/update Products from an uploaded .xlsx sheet.

    Rows are matched to existing products by their `ref` column; a blank ref
    creates a new product. Only columns present in the sheet's header row are
    written (partial-update semantics) — see import_service.py for the full
    validate-then-upsert contract.

    Args:
        file: The uploaded .xlsx file.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ImportSummary: Created/updated counts and any skipped-row errors.

    Raises:
        HTTPException: 422 if the uploaded file is not a valid .xlsx workbook.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    contents = await file.read()
    try:
        return await import_service.import_products(db, effective_brand_id, contents, access.actor_user)
    except InvalidWorkbookError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def get_product(
    product_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Fetch a single product by ID.

    Args:
        product_id: UUID of the product to fetch.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The product.
    """
    product = await product_service.get_product(db, access.effective_brand_id(brand_id), product_id)
    return ProductResponse.model_validate(product)


@router.patch("/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Update a product's mutable fields.

    Args:
        product_id: UUID of the product to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The updated product.
    """
    product = await product_service.update_product(
        db, access.effective_brand_id(brand_id), product_id, payload, access.actor_user
    )
    return ProductResponse.model_validate(product)


@router.delete(
    "/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK
)
async def deactivate_product(
    product_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Soft-delete a product (set is_active=False).

    Args:
        product_id: UUID of the product to deactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The deactivated product.
    """
    product = await product_service.deactivate_product(
        db, access.effective_brand_id(brand_id), product_id, access.actor_user
    )
    return ProductResponse.model_validate(product)


@router.post(
    "/{product_id}/activate", response_model=ProductResponse, status_code=status.HTTP_200_OK
)
async def activate_product(
    product_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Reactivate a previously deactivated product (idempotent — Stage 20 table view).

    Args:
        product_id: UUID of the product to reactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The reactivated product.
    """
    product = await product_service.set_product_active_state(
        db, access.effective_brand_id(brand_id), product_id, True, access.actor_user
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
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Upload or replace the product photo.

    Accepts JPEG, PNG, or WebP images up to 500 KB. Stores the image in
    Supabase Storage and saves the public URL on the product row.

    Args:
        product_id: UUID of the product to attach the photo to.
        file: The uploaded image file.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ProductResponse: The product with the updated photo_url.
    """
    product = await product_service.upload_photo(
        db, access.effective_brand_id(brand_id), product_id, file, access.actor_user
    )
    return ProductResponse.model_validate(product)
