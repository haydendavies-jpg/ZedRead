"""Reporting Group management routes — list, create, rename, delete (Stage 16).

Accessible to management JWT users and portal admins via resolve_catalog_access.
POS terminal JWT users can list reporting groups (read-only); write operations
require a management or portal JWT, mirroring categories.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.import_export import ImportSummary
from app.schemas.reporting_group import ReportingGroupCreate, ReportingGroupOut, ReportingGroupUpdate
from app.services import export_service, import_service, reporting_group_service
from app.services.import_service import InvalidWorkbookError
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/reporting-groups", tags=["reporting-groups"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from reporting group write operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reporting group management requires a management or portal JWT",
        )


@router.get("", response_model=list[ReportingGroupOut], status_code=status.HTTP_200_OK)
async def list_reporting_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[ReportingGroupOut]:
    """
    List reporting groups for the authenticated user's brand.

    Args:
        skip: Pagination offset.
        limit: Maximum number of reporting groups to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[ReportingGroupOut]: Reporting groups, default group first.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    groups = await reporting_group_service.list_reporting_groups(db, effective_brand_id, skip, limit)
    return [ReportingGroupOut.model_validate(g) for g in groups]


@router.post("", response_model=ReportingGroupOut, status_code=status.HTTP_201_CREATED)
async def create_reporting_group(
    payload: ReportingGroupCreate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ReportingGroupOut:
    """
    Create a new reporting group.

    Args:
        payload: Reporting group creation data.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ReportingGroupOut: The created reporting group.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    group = await reporting_group_service.create_reporting_group(
        db, effective_brand_id, payload, access.actor_user
    )
    return ReportingGroupOut.model_validate(group)


@router.patch("/{reporting_group_id}", response_model=ReportingGroupOut, status_code=status.HTTP_200_OK)
async def update_reporting_group(
    reporting_group_id: uuid.UUID,
    payload: ReportingGroupUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ReportingGroupOut:
    """
    Rename a reporting group. The system default group cannot be renamed.

    Args:
        reporting_group_id: UUID of the reporting group to update.
        payload: Fields to update.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        ReportingGroupOut: The updated reporting group.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    group = await reporting_group_service.update_reporting_group(
        db, effective_brand_id, reporting_group_id, payload, access.actor_user
    )
    return ReportingGroupOut.model_validate(group)


@router.delete("/{reporting_group_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_reporting_group(
    reporting_group_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a reporting group. Blocked for the default group or one still in use.

    Args:
        reporting_group_id: UUID of the reporting group to delete.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    await reporting_group_service.delete_reporting_group(
        db, effective_brand_id, reporting_group_id, access.actor_user
    )


@router.get("/export/template", response_model=None, status_code=status.HTTP_200_OK)
async def export_reporting_groups_template(
    access: CatalogAccess = Depends(resolve_catalog_access),
) -> Response:
    """
    Download a blank Reporting Groups import template (header row + example row).

    response_model is intentionally omitted — the body is a binary .xlsx file,
    not a JSON payload a Pydantic model could describe.

    Args:
        access: Resolved catalog access (required so the route stays authenticated).

    Returns:
        Response: The .xlsx template file.
    """
    wb = await export_service.build_reporting_groups_template()
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=reporting_groups_template.xlsx"},
    )


@router.get("/export", response_model=None, status_code=status.HTTP_200_OK)
async def export_reporting_groups(
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the brand's current Reporting Groups as a re-importable .xlsx file.

    Args:
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        Response: The .xlsx export file.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    wb = await export_service.build_reporting_groups_export(db, effective_brand_id)
    return Response(
        content=export_service.workbook_to_bytes(wb),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": "attachment; filename=reporting_groups_export.xlsx"},
    )


@router.post("/import", response_model=ImportSummary, status_code=status.HTTP_200_OK)
async def import_reporting_groups(
    file: UploadFile,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """
    Bulk create/update Reporting Groups from an uploaded .xlsx sheet.

    Rows are matched to existing groups by their `ref` column; a blank ref
    creates a new group. Only columns present in the sheet's header row are
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
        return await import_service.import_reporting_groups(
            db, effective_brand_id, contents, access.actor_user
        )
    except InvalidWorkbookError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
