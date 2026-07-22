"""Business logic for POS device registration and deregistration."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    DEVICE_DELETED,
    DEVICE_DEREGISTERED,
    DEVICE_REGISTERED,
    DEVICE_RENAMED,
)
from app.constants.statuses import LicenseStatus
from app.models.invoice import Invoice
from app.models.license import License
from app.models.register_session import RegisterSession
from app.models.user import User
from app.models.pos_device import PosDevice
from app.models.site import Site
from app.schemas.pos_device import PosDeviceRegister
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, device_id: uuid.UUID) -> PosDevice:
    """
    Fetch a PosDevice by ID or raise HTTP 404.

    Args:
        db: Active database session.
        device_id: UUID of the device.

    Returns:
        PosDevice: The found device.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(select(PosDevice).where(PosDevice.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


async def list_devices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[PosDevice]:
    """
    Return a paginated list of all registered devices.

    Args:
        db: Active database session.
        skip: Number of rows to skip.
        limit: Maximum rows to return.

    Returns:
        list[PosDevice]: The requested page of devices.
    """
    result = await db.execute(
        select(PosDevice).order_by(PosDevice.registered_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def count_active_devices_for_license(db: AsyncSession, license_id: uuid.UUID) -> int:
    """
    Count active PosDevice rows currently consuming a seat on a license.

    Used by pos_auth_service's self-service claim/re-pair flow to enforce
    License.max_devices — counted live from pos_devices rather than a
    separate mutable counter column, so it can never drift out of sync.

    Args:
        db: Active database session.
        license_id: The license to count seats against.

    Returns:
        int: Number of active devices currently claiming a seat.
    """
    result = await db.execute(
        select(func.count())
        .select_from(PosDevice)
        .where(PosDevice.license_id == license_id, PosDevice.is_active == True)  # noqa: E712
    )
    return result.scalar_one()


async def list_devices_for_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 200,
) -> list[PosDevice]:
    """
    List devices within a brand, optionally narrowed to one site.

    Backs the management portal's scoped Devices page (as opposed to the
    superadmin-only list_devices() above, which sees every device).

    Args:
        db: Active database session.
        brand_id: Brand to scope the listing to.
        site_id: Optional site filter within the brand.
        skip: Number of rows to skip.
        limit: Maximum rows to return.

    Returns:
        list[PosDevice]: Matching devices, most recently registered first.
    """
    query = (
        select(PosDevice).join(Site, Site.id == PosDevice.site_id).where(Site.brand_id == brand_id)
    )
    if site_id is not None:
        query = query.where(PosDevice.site_id == site_id)
    query = query.order_by(PosDevice.registered_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_device(db: AsyncSession, device_id: uuid.UUID) -> PosDevice:
    """
    Fetch a single device by ID.

    Args:
        db: Active database session.
        device_id: UUID of the device.

    Returns:
        PosDevice: The found device.

    Raises:
        HTTPException: 404 if not found.
    """
    return await _get_or_404(db, device_id)


async def register_device(
    db: AsyncSession,
    payload: PosDeviceRegister,
    actor: User,
) -> PosDevice:
    """
    Register a new POS device under a site and license, writing an audit log row.

    Args:
        db: Active database session.
        payload: Device registration data including the unique hardware token.
        actor: The authenticated portal user performing the registration.

    Returns:
        PosDevice: The newly registered device.

    Raises:
        HTTPException: 404 if the site or license does not exist.
        HTTPException: 409 if the device_token is already registered.
        HTTPException: 422 if the license does not belong to the given site.
        HTTPException: 422 if the license is not active.
    """
    # Validate site exists
    site_result = await db.execute(select(Site).where(Site.id == payload.site_id))
    if site_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    # Validate license exists and belongs to this site
    lic_result = await db.execute(select(License).where(License.id == payload.license_id))
    lic = lic_result.scalar_one_or_none()
    if lic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="License not found")

    if lic.site_id != payload.site_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="License does not belong to the specified site",
        )

    if lic.status != LicenseStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot register a device against an inactive license",
        )

    # Reject duplicate device tokens
    existing = await db.execute(
        select(PosDevice).where(PosDevice.device_token == payload.device_token)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A device with this token is already registered",
        )

    log.info("device.registering", site_id=str(payload.site_id), license_id=str(payload.license_id))

    device = PosDevice(
        id=uuid.uuid4(),
        site_id=payload.site_id,
        license_id=payload.license_id,
        device_name=payload.device_name,
        device_token=payload.device_token,
        hardware_id=payload.hardware_id,
        is_active=True,
    )
    db.add(device)

    await log_action(
        db=db,
        action=DEVICE_REGISTERED,
        entity_type="pos_device",
        entity_id=str(device.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={
            "site_id": str(device.site_id),
            "license_id": str(device.license_id),
            "device_name": device.device_name,
        },
    )

    await db.commit()
    await db.refresh(device)
    log.info("device.registered", device_id=str(device.id))
    return device


async def deregister_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    actor: User,
) -> PosDevice:
    """
    Deregister a POS device (set is_active = False) and write an audit log row.

    Args:
        db: Active database session.
        device_id: UUID of the device to deregister.
        actor: The authenticated portal user performing the action.

    Returns:
        PosDevice: The updated (deregistered) device.

    Raises:
        HTTPException: 404 if not found.
        HTTPException: 409 if the device is already deregistered.
    """
    device = await _get_or_404(db, device_id)

    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device is already deregistered",
        )

    device.is_active = False

    await log_action(
        db=db,
        action=DEVICE_DEREGISTERED,
        entity_type="pos_device",
        entity_id=str(device.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(device)
    return device


async def update_device_name(
    db: AsyncSession,
    device_id: uuid.UUID,
    device_name: str,
    actor: User,
) -> PosDevice:
    """
    Rename a POS device and write an audit log row.

    Args:
        db: Active database session.
        device_id: UUID of the device to rename.
        device_name: The new display name.
        actor: The authenticated portal user performing the rename.

    Returns:
        PosDevice: The updated device.

    Raises:
        HTTPException: 404 if not found.
    """
    device = await _get_or_404(db, device_id)
    before_name = device.device_name
    device.device_name = device_name

    await log_action(
        db=db,
        action=DEVICE_RENAMED,
        entity_type="pos_device",
        entity_id=str(device.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"device_name": before_name},
        after_state={"device_name": device_name},
    )

    await db.commit()
    await db.refresh(device)
    return device


async def hard_delete_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    actor: User,
) -> tuple[int, int]:
    """
    Permanently delete a POS device record, admin-only clean-up for stray/test
    registrations — irreversible, unlike deregister_device()'s soft-delete.

    A device may have register_sessions (ondelete=RESTRICT) that in turn have
    invoices referencing them (also ondelete=RESTRICT, but nullable) — neither
    is cascaded at the DB level, so this walks the chain itself: any invoice
    referencing one of the device's sessions is detached first (its
    register_session_id set NULL, keeping the invoice itself intact), then the
    sessions are deleted, then the device. user_pos_sessions.device_id is
    ondelete=SET NULL and needs no handling here — the DB does it automatically
    on the final delete.

    Args:
        db: Active database session.
        device_id: UUID of the device to delete.
        actor: The authenticated portal user performing the deletion.

    Returns:
        tuple[int, int]: (register_sessions_deleted, invoices_detached).

    Raises:
        HTTPException: 404 if not found.
    """
    device = await _get_or_404(db, device_id)

    session_ids_result = await db.execute(
        select(RegisterSession.id).where(RegisterSession.device_id == device_id)
    )
    session_ids = [row[0] for row in session_ids_result.all()]

    invoices_detached = 0
    if session_ids:
        detach_result = await db.execute(
            update(Invoice)
            .where(Invoice.register_session_id.in_(session_ids))
            .values(register_session_id=None)
        )
        invoices_detached = detach_result.rowcount or 0

        await db.execute(delete(RegisterSession).where(RegisterSession.device_id == device_id))

    log.info(
        "device.deleting",
        device_id=str(device_id),
        register_sessions_deleted=len(session_ids),
        invoices_detached=invoices_detached,
    )

    await log_action(
        db=db,
        action=DEVICE_DELETED,
        entity_type="pos_device",
        entity_id=str(device.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={
            "device_name": device.device_name,
            "site_id": str(device.site_id),
            "license_id": str(device.license_id),
            "register_sessions_deleted": len(session_ids),
            "invoices_detached": invoices_detached,
        },
    )

    await db.delete(device)
    await db.commit()
    return len(session_ids), invoices_detached
