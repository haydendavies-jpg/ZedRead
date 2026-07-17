"""Business logic for portal user management (Admin-role SuperAdmin only)."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    PORTAL_USER_ACTIVATED,
    PORTAL_USER_CREATED,
    PORTAL_USER_SUSPENDED,
    PORTAL_USER_UPDATED,
)
from app.models.superadmin import SuperAdmin
from app.schemas.superadmin import SuperAdminCreate, SuperAdminUpdate
from app.services.audit_service import log_action
from app.utils.security import hash_password, normalize_email

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, user_id: uuid.UUID) -> SuperAdmin:
    """
    Fetch a SuperAdmin by ID or raise HTTP 404.

    Args:
        db: Active database session.
        user_id: The UUID of the portal user.

    Returns:
        SuperAdmin: The found user.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    result = await db.execute(select(SuperAdmin).where(SuperAdmin.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal user not found")
    return user


async def list_superadmins(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> list[SuperAdmin]:
    """
    Return a paginated list of all portal users with optional filters.

    Args:
        db: Active database session.
        skip: Number of records to skip.
        limit: Maximum records to return.
        email: Optional substring filter on SuperAdmin.email (case-insensitive).
        role: Optional exact-match filter on SuperAdmin.role.
        is_active: Optional exact-match filter on SuperAdmin.is_active.

    Returns:
        list[SuperAdmin]: The requested page of portal users.
    """
    conditions: list = []
    if email is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(SuperAdmin.email.ilike(f"%{email}%"))
    if role is not None:
        conditions.append(SuperAdmin.role == role)
    if is_active is not None:
        conditions.append(SuperAdmin.is_active == is_active)

    result = await db.execute(
        select(SuperAdmin).where(*conditions).order_by(SuperAdmin.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_superadmin(db: AsyncSession, user_id: uuid.UUID) -> SuperAdmin:
    """
    Fetch a single portal user by ID.

    Args:
        db: Active database session.
        user_id: The UUID of the portal user.

    Returns:
        SuperAdmin: The found user.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    return await _get_or_404(db, user_id)


async def create_superadmin(
    db: AsyncSession,
    payload: SuperAdminCreate,
    actor: SuperAdmin,
) -> SuperAdmin:
    """
    Create a new portal user and write an audit log row in the same transaction.

    Args:
        db: Active database session.
        payload: The user creation data.
        actor: The authenticated Admin-role SuperAdmin performing the action.

    Returns:
        SuperAdmin: The newly created portal user.

    Raises:
        HTTPException: 409 if the email address is already taken.
    """
    # Emails are case-insensitive for login — normalize before storing/comparing
    # so "Jane@x.com" and "jane@x.com" are always the same account.
    email = normalize_email(payload.email)

    # Check for duplicate email before hashing the password (cheaper failure path)
    existing = await db.execute(select(SuperAdmin).where(func.lower(SuperAdmin.email) == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A portal user with this email already exists",
        )

    log.info("superadmin.creating", email=email, role=payload.role)

    user = SuperAdmin(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)

    await log_action(
        db=db,
        action=PORTAL_USER_CREATED,
        entity_type="superadmin",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"email": user.email, "role": user.role},
    )

    await db.commit()
    await db.refresh(user)
    log.info("superadmin.created", user_id=str(user.id))
    return user


async def update_superadmin(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: SuperAdminUpdate,
    actor: SuperAdmin,
) -> SuperAdmin:
    """
    Update a portal user's name or role and write an audit log row.

    Args:
        db: Active database session.
        user_id: The UUID of the user to update.
        payload: The fields to update (all optional).
        actor: The authenticated Admin-role SuperAdmin performing the action.

    Returns:
        SuperAdmin: The updated portal user.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    user = await _get_or_404(db, user_id)

    before = {"name": user.name, "role": user.role}
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    after = {"name": user.name, "role": user.role}

    await log_action(
        db=db,
        action=PORTAL_USER_UPDATED,
        entity_type="superadmin",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state=before,
        after_state=after,
    )

    await db.commit()
    await db.refresh(user)
    return user


async def suspend_superadmin(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: SuperAdmin,
) -> SuperAdmin:
    """
    Suspend a portal user (set is_active = False) and write an audit log row.

    An Admin-role SuperAdmin cannot suspend themselves.

    Args:
        db: Active database session.
        user_id: The UUID of the user to suspend.
        actor: The authenticated Admin-role SuperAdmin performing the action.

    Returns:
        SuperAdmin: The suspended portal user.

    Raises:
        HTTPException: 400 if the actor tries to suspend themselves.
        HTTPException: 404 if the user does not exist.
        HTTPException: 409 if the user is already suspended.
    """
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend your own account",
        )

    user = await _get_or_404(db, user_id)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already suspended")

    user.is_active = False

    await log_action(
        db=db,
        action=PORTAL_USER_SUSPENDED,
        entity_type="superadmin",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": True},
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(user)
    return user


async def activate_superadmin(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: SuperAdmin,
) -> SuperAdmin:
    """
    Activate a portal user (set is_active = True) and write an audit log row.

    Args:
        db: Active database session.
        user_id: The UUID of the user to activate.
        actor: The authenticated Admin-role SuperAdmin performing the action.

    Returns:
        SuperAdmin: The activated portal user.

    Raises:
        HTTPException: 404 if the user does not exist.
        HTTPException: 409 if the user is already active.
    """
    user = await _get_or_404(db, user_id)

    if user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already active")

    user.is_active = True

    await log_action(
        db=db,
        action=PORTAL_USER_ACTIVATED,
        entity_type="superadmin",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(user)
    return user
