"""Combo routes — product combo groups and combo options.

Two routers: `router` is nested under a product (create/update/deactivate a
combo group, plus its options — a combo group always belongs to a parent
product); `list_router` is brand-scoped and lists combo groups across every
product, powering the Stage 22 combined Variants+Combos portal page.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.combo import (
    ComboGroupCreate,
    ComboGroupListItem,
    ComboGroupResponse,
    ComboGroupUpdate,
    ComboOptionCreate,
    ComboOptionResponse,
)
from app.schemas.import_export import ImportSummary
from app.services import export_service, import_service
from app.services.combo_service import (
    add_combo_option,
    create_combo_group,
    deactivate_combo_group,
    list_combo_groups,
    list_combo_groups_for_brand,
    list_combo_options,
    remove_combo_option,
    set_combo_group_active_state,
    update_combo_group,
)
from app.services.import_service import InvalidWorkbookError
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/products/{product_id}/combos", tags=["combos"])
list_router = APIRouter(prefix="/combos", tags=["combos"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from combo bulk-import operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Combo import requires a management or portal JWT",
        )


@router.get(
    "/groups",
    response_model=list[ComboGroupResponse],
    status_code=status.HTTP_200_OK,
)
async def list_product_combo_groups(
    product_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ComboGroupResponse]:
    """
    List combo groups for a product.

    Args:
        product_id: UUID of the parent product.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ComboGroupResponse]: Combo groups ordered by display_order.
    """
    groups = await list_combo_groups(db, access.effective_brand_id(brand_id), product_id, skip, limit)
    return [ComboGroupResponse.model_validate(g) for g in groups]


@router.post(
    "/groups",
    response_model=ComboGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_combo_group(
    product_id: uuid.UUID,
    payload: ComboGroupCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ComboGroupResponse:
    """
    Create a combo group for a product.

    Args:
        product_id: UUID of the parent product.
        payload: Combo group creation data.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ComboGroupResponse: The newly created combo group.
    """
    group = await create_combo_group(db, access.effective_brand_id(brand_id), product_id, payload, access.actor_user)
    return ComboGroupResponse.model_validate(group)


@router.get(
    "/groups/{group_id}/options",
    response_model=list[ComboOptionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_combo_group_options(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ComboOptionResponse]:
    """
    List options for a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group.
        skip: Pagination offset.
        limit: Maximum rows to return.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[ComboOptionResponse]: Options ordered by display_order.
    """
    options = await list_combo_options(db, group_id, skip, limit)
    return [ComboOptionResponse.model_validate(o) for o in options]


@router.post(
    "/groups/{group_id}/options",
    response_model=ComboOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_combo_group_option(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ComboOptionCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ComboOptionResponse:
    """
    Add a product as an option to a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group to add the option to.
        payload: Option data (product_id, price_delta_cents).
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ComboOptionResponse: The created option.
    """
    option = await add_combo_option(db, access.effective_brand_id(brand_id), group_id, payload, access.actor_user)
    return ComboOptionResponse.model_validate(option)


@router.patch(
    "/groups/{group_id}",
    response_model=ComboGroupResponse,
    status_code=status.HTTP_200_OK,
)
async def update_product_combo_group(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    payload: ComboGroupUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ComboGroupResponse:
    """
    Update a combo group's mutable fields (name, display_name, selection rules, order).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group to update.
        payload: Fields to update.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ComboGroupResponse: The updated combo group.
    """
    group = await update_combo_group(db, access.effective_brand_id(brand_id), group_id, payload, access.actor_user)
    return ComboGroupResponse.model_validate(group)


@router.delete(
    "/groups/{group_id}",
    response_model=ComboGroupResponse,
    status_code=status.HTTP_200_OK,
)
async def deactivate_product_combo_group(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ComboGroupResponse:
    """
    Soft-delete a combo group (set is_active=False).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group to deactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ComboGroupResponse: The deactivated combo group.
    """
    group = await deactivate_combo_group(db, access.effective_brand_id(brand_id), group_id, access.actor_user)
    return ComboGroupResponse.model_validate(group)


@router.post(
    "/groups/{group_id}/activate",
    response_model=ComboGroupResponse,
    status_code=status.HTTP_200_OK,
)
async def activate_product_combo_group(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ComboGroupResponse:
    """
    Reactivate a previously deactivated combo group (idempotent — Stage 22 table view).

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group to reactivate.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        ComboGroupResponse: The reactivated combo group.
    """
    group = await set_combo_group_active_state(
        db, access.effective_brand_id(brand_id), group_id, True, access.actor_user
    )
    return ComboGroupResponse.model_validate(group)


@router.delete(
    "/groups/{group_id}/options/{option_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_combo_group_option(
    product_id: uuid.UUID,
    group_id: uuid.UUID,
    option_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove an option from a combo group.

    Args:
        product_id: UUID of the parent product (used for URL consistency).
        group_id: UUID of the combo group (used for URL consistency).
        option_id: UUID of the option to remove.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.
    """
    await remove_combo_option(db, access.effective_brand_id(brand_id), option_id, access.actor_user)


# ── Brand-wide list, export, import (Stage 22) ─────────────────────────────────


@list_router.get("", response_model=list[ComboGroupListItem], status_code=status.HTTP_200_OK)
async def list_brand_combos(
    product_id: uuid.UUID | None = Query(None, description="Optional filter — only combo groups of this product"),
    include_inactive: bool = Query(False, description="Include soft-deleted combo groups"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ComboGroupListItem]:
    """
    List every combo group across the brand's catalog, joined to its parent product.

    Powers the Stage 22 combined Variants+Combos portal page.

    Args:
        product_id: Optional filter — only combo groups of this product.
        include_inactive: Include soft-deleted combo groups.
        skip: Pagination offset.
        limit: Maximum rows to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[ComboGroupListItem]: Combo groups ordered by product name, each
            carrying its joined product_name and product_ref.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    rows = await list_combo_groups_for_brand(db, effective_brand_id, product_id, include_inactive, skip, limit)
    return [
        ComboGroupListItem(
            **ComboGroupResponse.model_validate(group).model_dump(),
            product_name=product_name,
            product_ref=product_ref,
        )
        for group, product_name, product_ref in rows
    ]


@list_router.get("/export/template", response_model=None, status_code=status.HTTP_200_OK)
async def export_combos_template(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download a blank Combos import template (header row + example + product dropdown).

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx template file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_combos_template(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=combos_template.xlsx"},
    )


@list_router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_combos(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the brand's current Combos as a re-importable .xlsx file.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_combos_export(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=combos_export.xlsx"},
    )


@list_router.post("/import", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_combos(
    file: UploadFile,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """
    Bulk create/update Combos from an uploaded .xlsx sheet.

    Rows are matched to existing combo groups by their `ref` column; a blank
    ref creates a new combo group under the sheet's `product` column (matched
    by product ref). Only columns present in the sheet's header row are
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
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    contents = await file.read()
    try:
        return await import_service.import_combos(db, effective_brand_id, contents, access.actor_user)
    except InvalidWorkbookError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
