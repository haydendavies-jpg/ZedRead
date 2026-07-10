"""Category management routes — list, create, and update product categories.

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list categories (read-only); write operations require
management or portal JWT. All business logic lives in category_service.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.import_export import ImportSummary
from app.services import category_service, export_service, import_service
from app.services.import_service import InvalidWorkbookError
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/categories", tags=["categories"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_model=list[CategoryOut], status_code=status.HTTP_200_OK)
async def list_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    include_inactive: bool = Query(False, description="Include soft-deleted categories (Stage 20 table view)"),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryOut]:
    """
    List categories for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum number of categories to return.
        include_inactive: Include soft-deleted categories.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[CategoryOut]: Categories ordered by display_order.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    cats = await category_service.list_categories(db, effective_brand_id, skip, limit, include_inactive)
    return [CategoryOut.model_validate(c) for c in cats]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> CategoryOut:
    """
    Create a new product category.

    Args:
        payload: Category creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        CategoryOut: The created category.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Category management requires a management or portal JWT",
        )
    effective_brand_id = access.effective_brand_id(brand_id)
    cat = await category_service.create_category(db, effective_brand_id, payload, access.actor_user)
    return CategoryOut.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryOut, status_code=status.HTTP_200_OK)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> CategoryOut:
    """
    Update a category's mutable fields.

    System categories cannot be renamed or deactivated.

    Args:
        category_id: UUID of the category to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        CategoryOut: The updated category.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Category management requires a management or portal JWT",
        )
    effective_brand_id = access.effective_brand_id(brand_id)
    cat = await category_service.update_category(db, effective_brand_id, category_id, payload, access.actor_user)
    return CategoryOut.model_validate(cat)


@router.get("/export/template", response_model=None, status_code=status.HTTP_200_OK)
async def export_categories_template(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download a blank Categories import template (header row + example + reporting group dropdown).

    response_model is intentionally omitted — the body is a binary .xlsx file,
    not a JSON payload a Pydantic model could describe.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx template file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_categories_template(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=categories_template.xlsx"},
    )


@router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_categories(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the brand's current Categories as a re-importable .xlsx file.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_categories_export(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=categories_export.xlsx"},
    )


@router.post("/import", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_categories(
    file: UploadFile,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """
    Bulk create/update Categories from an uploaded .xlsx sheet.

    Rows are matched to existing categories by their `ref` column; a blank ref
    creates a new category. Only columns present in the sheet's header row are
    written (partial-update semantics) — see import_service.py.

    Args:
        file: The uploaded .xlsx file.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ImportSummary: Created/updated counts and any skipped-row errors.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
        HTTPException: 422 if the uploaded file is not a valid .xlsx workbook.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Category management requires a management or portal JWT",
        )
    effective_brand_id = access.effective_brand_id(brand_id)
    contents = await file.read()
    try:
        return await import_service.import_categories(db, effective_brand_id, contents, access.actor_user)
    except InvalidWorkbookError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
