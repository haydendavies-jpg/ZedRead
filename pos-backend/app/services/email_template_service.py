"""Business logic for EmailTemplate CRUD operations.

Email templates are global and managed only by Admin-role portal admins (User.superadmin_role) (route
layer enforces this via require_super_admin) — they back ZedRead's own
billing-info-request emails, not a tenant-facing feature.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import EMAIL_TEMPLATE_CREATED, EMAIL_TEMPLATE_UPDATED
from app.models.email_template import EmailTemplate
from app.models.user import User
from app.schemas.email_template import EmailTemplateCreate, EmailTemplateUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, template_id: uuid.UUID) -> EmailTemplate:
    """
    Fetch an EmailTemplate by ID or raise HTTP 404.

    Args:
        db: Active database session.
        template_id: UUID of the template to fetch.

    Returns:
        EmailTemplate: The found template.

    Raises:
        HTTPException: 404 if no template with that ID exists.
    """
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    return template


async def get_template_by_key(db: AsyncSession, template_key: str) -> EmailTemplate | None:
    """
    Fetch an active EmailTemplate by its stable template_key.

    Args:
        db: Active database session.
        template_key: The stable key (e.g. "billing_info_request").

    Returns:
        EmailTemplate | None: The active template, or None if missing/inactive.
    """
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.template_key == template_key,
            EmailTemplate.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def list_templates(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[EmailTemplate]:
    """
    Return a paginated list of all email templates.

    Args:
        db: Active database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.

    Returns:
        list[EmailTemplate]: The requested page of templates.
    """
    result = await db.execute(
        select(EmailTemplate).order_by(EmailTemplate.name).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> EmailTemplate:
    """
    Fetch a single email template by ID.

    Args:
        db: Active database session.
        template_id: UUID of the template.

    Returns:
        EmailTemplate: The found template.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    return await _get_or_404(db, template_id)


async def create_template(
    db: AsyncSession,
    payload: EmailTemplateCreate,
    actor: User,
) -> EmailTemplate:
    """
    Create a new, non-system email template and write an audit log row.

    Args:
        db: Active database session.
        payload: The template creation data.
        actor: The authenticated Admin-role portal admin performing the action.

    Returns:
        EmailTemplate: The newly created template.

    Raises:
        HTTPException: 409 if a template with the same template_key already exists.
    """
    existing = await db.execute(
        select(EmailTemplate).where(EmailTemplate.template_key == payload.template_key)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email template with key '{payload.template_key}' already exists",
        )

    template = EmailTemplate(
        id=uuid.uuid4(),
        template_key=payload.template_key,
        name=payload.name,
        subject=payload.subject,
        body=payload.body,
        is_system=False,
        is_active=True,
    )
    db.add(template)
    await db.flush()

    await log_action(
        db=db,
        action=EMAIL_TEMPLATE_CREATED,
        entity_type="email_template",
        entity_id=str(template.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "template_key": template.template_key,
            "name": template.name,
            "subject": template.subject,
            "is_active": template.is_active,
        },
    )

    await db.commit()
    await db.refresh(template)
    log.info("email_template.created", template_id=str(template.id), template_key=template.template_key)
    return template


async def update_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    payload: EmailTemplateUpdate,
    actor: User,
) -> EmailTemplate:
    """
    Update an email template's mutable fields and write an audit log row.

    Args:
        db: Active database session.
        template_id: UUID of the template to update.
        payload: The fields to update (all optional).
        actor: The authenticated Admin-role portal admin performing the action.

    Returns:
        EmailTemplate: The updated template.

    Raises:
        HTTPException: 404 if the template does not exist.
    """
    template = await _get_or_404(db, template_id)

    before = {
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "is_active": template.is_active,
    }
    if payload.name is not None:
        template.name = payload.name
    if payload.subject is not None:
        template.subject = payload.subject
    if payload.body is not None:
        template.body = payload.body
    if payload.is_active is not None:
        template.is_active = payload.is_active
    after = {
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "is_active": template.is_active,
    }

    await log_action(
        db=db,
        action=EMAIL_TEMPLATE_UPDATED,
        entity_type="email_template",
        entity_id=str(template.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(template)
    return template
