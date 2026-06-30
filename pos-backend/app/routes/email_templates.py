"""Routes for EmailTemplate management (Admin-role SuperAdmins only).

These templates back ZedRead's own billing-info-request emails — a global,
non-tenant-facing feature — so every route here is gated with
require_super_admin rather than the broader get_current_superadmin.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.superadmin import SuperAdmin
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateResponse, EmailTemplateUpdate
from app.services import email_template_service
from app.utils.dependencies import require_super_admin

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


@router.get("/", response_model=list[EmailTemplateResponse])
async def list_email_templates(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(require_super_admin),
) -> list[EmailTemplateResponse]:
    """List all email templates with pagination."""
    return await email_template_service.list_templates(db, skip=skip, limit=limit)


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: SuperAdmin = Depends(require_super_admin),
) -> EmailTemplateResponse:
    """Fetch a single email template by ID."""
    return await email_template_service.get_template(db, template_id)


@router.post("/", response_model=EmailTemplateResponse, status_code=201)
async def create_email_template(
    payload: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> EmailTemplateResponse:
    """Create a new, non-system email template."""
    return await email_template_service.create_template(db, payload, actor)


@router.patch("/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: uuid.UUID,
    payload: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    actor: SuperAdmin = Depends(require_super_admin),
) -> EmailTemplateResponse:
    """Update an email template's mutable fields (name, subject, body, is_active)."""
    return await email_template_service.update_template(db, template_id, payload, actor)
