"""Register (till) session reporting routes — filtered list only.

Read-only and reporting-scoped: the transactional open/close/current-lookup
flows the POS terminal drives live in routes/register_sessions.py and are
unaffected by this file — matching the invoices.py / invoice_reports.py split.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.register_session_report_service import (
    RegisterSessionReportRow,
    list_register_session_reports,
)
from app.utils.dependencies import CatalogAccess, resolve_catalog_access

router = APIRouter(prefix="/register-session-reports", tags=["register-session-reports"])


def _resolve_site_filter(access: CatalogAccess, site_id: uuid.UUID | None) -> uuid.UUID | None:
    """
    Resolve the effective site filter for a list request.

    POS terminal users and site-scope management users are pinned to their
    own site: an explicit site_id must match it, and an absent one defaults
    to it. Brand-scope, group-scope, and portal admin callers may filter by
    any site_id, or supply none to mean "every site in the brand".

    Args:
        access: The resolved catalog access context.
        site_id: The site_id query parameter, if supplied.

    Returns:
        uuid.UUID | None: The site_id to filter by, or None for "all sites".

    Raises:
        HTTPException: 403 if a POS/site-scope caller requests a different site.
    """
    own_site_id: uuid.UUID | None = None
    if access.pos_access:
        own_site_id = access.pos_access.site.id
    elif access.mgmt_access and access.mgmt_access.scope == "site" and access.mgmt_access.site:
        own_site_id = access.mgmt_access.site.id

    if own_site_id is None:
        return site_id
    if site_id is not None and site_id != own_site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: report scope exceeds your site",
        )
    return own_site_id


@router.get("", response_model=list[RegisterSessionReportRow], status_code=status.HTTP_200_OK)
async def list_register_sessions_report(
    site_id: uuid.UUID | None = Query(None, description="Filter by site"),
    device_id: uuid.UUID | None = Query(None, description="Filter by terminal"),
    session_status: str | None = Query(None, alias="status", description="open/closed"),
    start_date: date | None = Query(None, description="Lower bound on opened_at date (inclusive)"),
    end_date: date | None = Query(None, description="Upper bound on opened_at date (inclusive)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    brand_id: uuid.UUID | None = Query(None, description="Required for portal admin or group-scope access"),
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> list[RegisterSessionReportRow]:
    """
    List register sessions for the authenticated user's brand, filtered and
    most recently opened first — opening/closing cash, cash takings,
    variance, and who opened/closed each one.

    Args:
        site_id: Optional site filter.
        device_id: Optional terminal filter.
        session_status: Optional status filter — open/closed.
        start_date: Optional lower bound on the opened_at date (inclusive).
        end_date: Optional upper bound on the opened_at date (inclusive).
        skip: Pagination offset.
        limit: Maximum sessions to return.
        brand_id: Required for portal admin or group-scope access.
        access: Resolved catalog access (POS, management, or portal).
        db: Active database session.

    Returns:
        list[RegisterSessionReportRow]: Matching sessions ordered by opened_at descending.
    """
    effective_brand_id = access.effective_brand_id(brand_id)
    effective_site_id = _resolve_site_filter(access, site_id)
    return await list_register_session_reports(
        db,
        effective_brand_id,
        effective_site_id,
        device_id,
        session_status,
        start_date,
        end_date,
        skip,
        limit,
    )
