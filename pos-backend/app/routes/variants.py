"""Variant routes — product variants, attribute types, and attribute values.

Two routers: `router` is nested under a product (create/update/deactivate — a
variant is always created in the context of its parent product); `list_router`
is brand-scoped and lists variants across every product, powering the Stage 22
combined Variants+Combos portal page.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.import_export import ImportSummary
from app.schemas.variant import VariantCreate, VariantListItem, VariantResponse, VariantUpdate
from app.services import export_service, import_service
from app.services.import_service import InvalidWorkbookError
from app.services.variant_service import (
    create_variant,
    deactivate_variant,
    list_variants,
    list_variants_for_brand,
    set_variant_active_state,
    update_variant,
    variant_to_response,
)
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/products/{product_id}/variants", tags=["variants"])
list_router = APIRouter(prefix="/variants", tags=["variants"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from variant bulk-import operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Variant import requires a management or portal JWT",
        )


@router.get("", response_model=list[VariantResponse], status_code=status.HTTP_200_OK)
async def list_product_variants(
    product_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[VariantResponse]:
    """
    List active variants for a product.

    Args:
        product_id: UUID of the parent product.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[VariantResponse]: Active variants with attribute data.
    """
    return await list_variants(db, access.effective_brand_id(brand_id), product_id, skip, limit)


@router.post("", response_model=VariantResponse, status_code=status.HTTP_201_CREATED)
async def create_product_variant(
    product_id: uuid.UUID,
    payload: VariantCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Create a variant for a product.

    Args:
        product_id: UUID of the parent product.
        payload: Variant data including attribute assignments.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        VariantResponse: The newly created variant.
    """
    return await create_variant(db, access.effective_brand_id(brand_id), product_id, payload, access.actor_user)


@router.patch("/{variant_id}", response_model=VariantResponse, status_code=status.HTTP_200_OK)
async def update_product_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Update a variant's price or SKU.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        variant_id: UUID of the variant to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        VariantResponse: The updated variant.
    """
    return await update_variant(db, access.effective_brand_id(brand_id), variant_id, payload, access.actor_user)


@router.delete("/{variant_id}", response_model=VariantResponse, status_code=status.HTTP_200_OK)
async def deactivate_product_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Soft-delete a variant (set is_active=False).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        variant_id: UUID of the variant to deactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        VariantResponse: The deactivated variant.
    """
    return await deactivate_variant(db, access.effective_brand_id(brand_id), variant_id, access.actor_user)


@router.post("/{variant_id}/activate", response_model=VariantResponse, status_code=status.HTTP_200_OK)
async def activate_product_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> VariantResponse:
    """
    Reactivate a previously deactivated variant (idempotent — Stage 22 table view).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        variant_id: UUID of the variant to reactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        VariantResponse: The reactivated variant.
    """
    return await set_variant_active_state(
        db, access.effective_brand_id(brand_id), variant_id, True, access.actor_user
    )


# ── Brand-wide list, export, import (Stage 22) ─────────────────────────────────


@list_router.get("", response_model=list[VariantListItem], status_code=status.HTTP_200_OK)
async def list_brand_variants(
    product_id: uuid.UUID | None = Query(None, description="Optional filter — only variants of this product"),
    include_inactive: bool = Query(False, description="Include soft-deleted variants"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[VariantListItem]:
    """
    List every variant across the brand's catalog, joined to its parent product.

    Powers the Stage 22 combined Variants+Combos portal page.

    Args:
        product_id: Optional filter — only variants of this product.
        include_inactive: Include soft-deleted variants.
        skip: Pagination offset.
        limit: Maximum rows to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[VariantListItem]: Variants ordered by product name, each carrying
            its joined product_name and product_ref.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    rows = await list_variants_for_brand(db, effective_brand_id, product_id, include_inactive, skip, limit)
    items = []
    for variant, product_name, product_ref in rows:
        response = await variant_to_response(db, variant)
        items.append(
            VariantListItem(**response.model_dump(), product_name=product_name, product_ref=product_ref)
        )
    return items


@list_router.get("/export/template", response_model=None, status_code=status.HTTP_200_OK)
async def export_variants_template(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download a blank Variants import template (header row + example + product dropdown).

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx template file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_variants_template(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=variants_template.xlsx"},
    )


@list_router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_variants(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the brand's current Variants as a re-importable .xlsx file.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_variants_export(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=variants_export.xlsx"},
    )


@list_router.post("/import", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_variants(
    file: UploadFile,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """
    Bulk update Variants from an uploaded .xlsx sheet.

    Update-only: rows are matched to existing variants by their `ref` column.
    Creating a new variant via import is not supported — attribute assignment
    (which varies per brand) doesn't fit the fixed-header Stage 19 template
    model, so new variants must still be created from the Product page. A row
    with a blank ref is reported as an error rather than silently skipped.

    Args:
        file: The uploaded .xlsx file.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ImportSummary: Updated counts and any skipped-row errors.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
        HTTPException: 422 if the uploaded file is not a valid .xlsx workbook.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    contents = await file.read()
    try:
        return await import_service.import_variants(db, effective_brand_id, contents, access.actor_user)
    except InvalidWorkbookError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
