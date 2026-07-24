"""Print template management routes, plus the POS read contract GET /pos/print-config.

Management CRUD lives under /print-templates (portal/management JWT only).
The POS terminal consumes everything it needs — printer locations, every
template with its elements, and resolved company-profile fields — from one
GET /pos/print-config?site_id= call, fetched on sync (not polled), mirroring
routes/menu_layouts.py's /menu-layouts + /pos/menu-layout split.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.print_fields import SECTION_PRINT_ORDER
from app.database import get_db
from app.models.site import Site
from app.schemas.print_template import (
    PosPrintConfigResponse,
    PrintTemplateDetail,
    PrintTemplateElementOut,
    PrintTemplateElementsReplace,
    PrintTemplateOut,
    PrintTemplateUpdate,
)
from app.services import print_template_service
from app.services.report_service import _assert_site_scope
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/print-templates", tags=["print-templates"])
pos_router = APIRouter(prefix="/pos", tags=["pos"])


def _require_management(access: CatalogAccess) -> None:
    """
    Reject POS terminal tokens from print-template write operations.

    Args:
        access: Resolved catalog access for the current request.

    Raises:
        HTTPException: 403 if the caller authenticated with a POS terminal JWT.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Print template management requires a management or portal JWT",
        )


def _to_detail(template) -> PrintTemplateDetail:
    """Build a PrintTemplateDetail from a PrintTemplate ORM row, sorting its elements print-order."""
    base = PrintTemplateOut.model_validate(template).model_dump()
    elements = sorted(template.elements, key=lambda e: (SECTION_PRINT_ORDER[e.section], e.display_order))
    return PrintTemplateDetail(**base, elements=[PrintTemplateElementOut.model_validate(e) for e in elements])


@router.get("", response_model=list[PrintTemplateOut], status_code=status.HTTP_200_OK)
async def list_print_templates(
    template_type: str | None = Query(None, description="Filter: invoice | docket | register_summary | cash_in_slip"),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[PrintTemplateOut]:
    """
    List print templates for the authenticated user's brand.

    Args:
        template_type: Optional type filter.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        list[PrintTemplateOut]: Matching templates, name order.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    templates = await print_template_service.list_templates(db, effective_brand_id, template_type)
    return [PrintTemplateOut.model_validate(t) for t in templates]


@router.get("/{template_id}", response_model=PrintTemplateDetail, status_code=status.HTTP_200_OK)
async def get_print_template(
    template_id: uuid.UUID,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PrintTemplateDetail:
    """
    Fetch one print template with its ordered elements.

    Args:
        template_id: UUID of the template to fetch.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        PrintTemplateDetail: The template and its elements.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    template = await print_template_service.get_template_detail(db, effective_brand_id, template_id)
    return _to_detail(template)


@router.patch("/{template_id}", response_model=PrintTemplateOut, status_code=status.HTTP_200_OK)
async def update_print_template(
    template_id: uuid.UUID,
    payload: PrintTemplateUpdate,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PrintTemplateOut:
    """
    Rename a print template.

    Args:
        template_id: UUID of the template to rename.
        payload: The new name.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        PrintTemplateOut: The updated template.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    template = await print_template_service.update_template(db, effective_brand_id, template_id, payload, access.actor_user)
    return PrintTemplateOut.model_validate(template)


@router.put("/{template_id}/elements", response_model=PrintTemplateDetail, status_code=status.HTTP_200_OK)
async def replace_print_template_elements(
    template_id: uuid.UUID,
    payload: PrintTemplateElementsReplace,
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PrintTemplateDetail:
    """
    Replace a print template's complete, ordered element list — the editor's Save action.

    Args:
        template_id: UUID of the template to update.
        payload: The template's new complete element list.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access.
        db: Active database session.

    Returns:
        PrintTemplateDetail: The updated template and its new elements.
    """
    _require_management(access)
    effective_brand_id = access.effective_brand_id(brand_id)
    template = await print_template_service.replace_elements(
        db, effective_brand_id, template_id, payload.elements, access.actor_user
    )
    return _to_detail(template)


# ── POS consumption contract ──────────────────────────────────────────────────


@pos_router.get("/print-config", response_model=PosPrintConfigResponse, status_code=status.HTTP_200_OK)
async def get_pos_print_config(
    site_id: uuid.UUID = Query(..., description="Site to resolve print config for"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> PosPrintConfigResponse:
    """
    Fetch-on-sync contract for the Android app: every printer location, every
    print template (with elements) for the site's brand, and resolved
    company-profile fields — fetched once per sync, never polled.

    Args:
        site_id: Site to resolve print config for.
        access: Resolved catalog access (POS or site-scoped management).
        db: Active database session.

    Returns:
        PosPrintConfigResponse: Locations, templates, and company-profile fields.
    """
    if access.pos_access:
        _assert_site_scope(site_id, access.pos_access.site.id)
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        _assert_site_scope(site_id, access.mgmt_access.site.id)

    site_result = await db.execute(select(Site).where(Site.id == site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    return await print_template_service.get_pos_print_config(db, site)
