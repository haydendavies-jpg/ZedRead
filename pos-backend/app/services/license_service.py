"""Business logic for license CRUD and status management."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    LICENSE_CREATED,
    LICENSE_DISABLED,
    LICENSE_ENABLED,
    LICENSE_UPDATED,
)
from app.constants.statuses import LicenseStatus
from app.models.license import License
from app.models.user import User
from app.models.site import Site
from app.schemas.license import LicenseCreate, LicenseUpdate
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, license_id: uuid.UUID) -> License:
    """
    Fetch a License by ID or raise HTTP 404.

    Args:
        db: Active database session.
        license_id: UUID of the license to fetch.

    Returns:
        License: The found license.

    Raises:
        HTTPException: 404 if no license with that ID exists.
    """
    result = await db.execute(select(License).where(License.id == license_id))
    lic = result.scalar_one_or_none()
    if lic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")
    return lic


async def list_licenses(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    site_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[License]:
    """
    Return a paginated list of all licenses with optional filters.

    Args:
        db: Active database session.
        skip: Number of rows to skip.
        limit: Maximum rows to return.
        site_id: Optional exact-match filter on License.site_id.
        status: Optional exact-match filter on License.status.

    Returns:
        list[License]: The requested page of licenses.
    """
    conditions: list = []
    if site_id is not None:
        conditions.append(License.site_id == site_id)
    if status is not None:
        conditions.append(License.status == status)

    result = await db.execute(
        select(License).where(*conditions).order_by(License.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_license(db: AsyncSession, license_id: uuid.UUID) -> License:
    """
    Fetch a single license by ID.

    Args:
        db: Active database session.
        license_id: UUID of the license.

    Returns:
        License: The found license.

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, license_id)


async def create_license(
    db: AsyncSession,
    payload: LicenseCreate,
    actor: User,
) -> License:
    """
    Create a new license for a site and write an audit log row in the same transaction.

    Args:
        db: Active database session.
        payload: License creation data.
        actor: The authenticated portal user performing the action.

    Returns:
        License: The newly created license.

    Raises:
        HTTPException: 404 if the referenced site does not exist.
        HTTPException: 409 if the site already has a license.
        HTTPException: 422 if expires_at is not after starts_at.
    """
    # Validate site exists
    site_result = await db.execute(select(Site).where(Site.id == payload.site_id))
    if site_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    # Validate date range
    if payload.expires_at <= payload.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expires_at must be after starts_at",
        )

    # Enforce one license per site
    existing = await db.execute(select(License).where(License.site_id == payload.site_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This site already has a license",
        )

    log.info("license.creating", site_id=str(payload.site_id))

    lic = License(
        id=uuid.uuid4(),
        site_id=payload.site_id,
        plan_name=payload.plan_name,
        status=LicenseStatus.ACTIVE.value,
        monthly_fee_cents=payload.monthly_fee_cents,
        is_trial=payload.is_trial,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        max_devices=payload.max_devices,
    )
    db.add(lic)

    await log_action(
        db=db,
        action=LICENSE_CREATED,
        entity_type="license",
        entity_id=str(lic.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "site_id": str(lic.site_id),
            "plan_name": lic.plan_name,
            "status": lic.status,
            "monthly_fee_cents": lic.monthly_fee_cents,
            "max_devices": lic.max_devices,
        },
    )

    await db.commit()
    await db.refresh(lic)
    log.info("license.created", license_id=str(lic.id))
    return lic


async def update_license(
    db: AsyncSession,
    license_id: uuid.UUID,
    payload: LicenseUpdate,
    actor: User,
) -> License:
    """
    Update mutable fields on a license and write an audit log row.

    Args:
        db: Active database session.
        license_id: UUID of the license to update.
        payload: Fields to update (all optional).
        actor: The authenticated portal user performing the action.

    Returns:
        License: The updated license.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 422 if the new expires_at is not after starts_at.
    """
    lic = await _get_or_404(db, license_id)

    before = {
        "plan_name": lic.plan_name,
        "monthly_fee_cents": lic.monthly_fee_cents,
        "expires_at": lic.expires_at.isoformat(),
        "max_devices": lic.max_devices,
    }

    if payload.plan_name is not None:
        lic.plan_name = payload.plan_name
    if payload.monthly_fee_cents is not None:
        lic.monthly_fee_cents = payload.monthly_fee_cents
    if payload.expires_at is not None:
        if payload.expires_at <= lic.starts_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at must be after starts_at",
            )
        lic.expires_at = payload.expires_at
    if payload.max_devices is not None:
        lic.max_devices = payload.max_devices

    after = {
        "plan_name": lic.plan_name,
        "monthly_fee_cents": lic.monthly_fee_cents,
        "expires_at": lic.expires_at.isoformat(),
        "max_devices": lic.max_devices,
    }

    await log_action(
        db=db,
        action=LICENSE_UPDATED,
        entity_type="license",
        entity_id=str(lic.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(lic)
    return lic


async def disable_license(
    db: AsyncSession,
    license_id: uuid.UUID,
    actor: User,
) -> License:
    """
    Disable an active license (manual suspension).

    Args:
        db: Active database session.
        license_id: UUID of the license to disable.
        actor: The authenticated portal user performing the action.

    Returns:
        License: The updated license.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if the license is already disabled.
    """
    lic = await _get_or_404(db, license_id)

    if lic.status == LicenseStatus.DISABLED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="License is already disabled")

    lic.status = LicenseStatus.DISABLED.value

    await log_action(
        db=db,
        action=LICENSE_DISABLED,
        entity_type="license",
        entity_id=str(lic.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": LicenseStatus.ACTIVE.value},
        after_state={"status": LicenseStatus.DISABLED.value},
    )

    await db.commit()
    await db.refresh(lic)
    return lic


async def enable_license(
    db: AsyncSession,
    license_id: uuid.UUID,
    actor: User,
) -> License:
    """
    Re-enable a disabled license.

    Args:
        db: Active database session.
        license_id: UUID of the license to enable.
        actor: The authenticated portal user performing the action.

    Returns:
        License: The updated license.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if the license is not currently disabled.
    """
    lic = await _get_or_404(db, license_id)

    if lic.status != LicenseStatus.DISABLED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only disabled licenses can be re-enabled",
        )

    lic.status = LicenseStatus.ACTIVE.value

    await log_action(
        db=db,
        action=LICENSE_ENABLED,
        entity_type="license",
        entity_id=str(lic.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"status": LicenseStatus.DISABLED.value},
        after_state={"status": LicenseStatus.ACTIVE.value},
    )

    await db.commit()
    await db.refresh(lic)
    return lic
