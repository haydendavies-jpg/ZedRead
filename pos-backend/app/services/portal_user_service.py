"""Business logic for portal user management (super_admin only)."""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    PORTAL_USER_ACTIVATED,
    PORTAL_USER_CREATED,
    PORTAL_USER_SUSPENDED,
)
from app.models.portal_user import PortalUser
from app.schemas.portal_user import PortalUserCreate, PortalUserUpdate
from app.services.audit_service import log_action
from app.utils.security import hash_password

log = structlog.get_logger(__name__)


async def _get_or_404(db: AsyncSession, user_id: uuid.UUID) -> PortalUser:
    """
    Fetch a PortalUser by ID or raise HTTP 404.

    Args:
        db: Active database session.
        user_id: The UUID of the portal user.

    Returns:
        PortalUser: The found user.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    result = await db.execute(select(PortalUser).where(PortalUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal user not found")
    return user


async def list_portal_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    email: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> list[PortalUser]:
    """
    Return a paginated list of all portal users with optional filters.

    Args:
        db: Active database session.
        skip: Number of records to skip.
        limit: Maximum records to return.
        email: Optional substring filter on PortalUser.email (case-insensitive).
        role: Optional exact-match filter on PortalUser.role.
        is_active: Optional exact-match filter on PortalUser.is_active.

    Returns:
        list[PortalUser]: The requested page of portal users.
    """
    conditions: list = []
    if email is not None:
        # Case-insensitive partial match using SQL ILIKE
        conditions.append(PortalUser.email.ilike(f"%{email}%"))
    if role is not None:
        conditions.append(PortalUser.role == role)
    if is_active is not None:
        conditions.append(PortalUser.is_active == is_active)

    result = await db.execute(
        select(PortalUser).where(*conditions).order_by(PortalUser.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_portal_user(db: AsyncSession, user_id: uuid.UUID) -> PortalUser:
    """
    Fetch a single portal user by ID.

    Args:
        db: Active database session.
        user_id: The UUID of the portal user.

    Returns:
        PortalUser: The found user.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    return await _get_or_404(db, user_id)


async def create_portal_user(
    db: AsyncSession,
    payload: PortalUserCreate,
    actor: PortalUser,
) -> PortalUser:
    """
    Create a new portal user and write an audit log row in the same transaction.

    Args:
        db: Active database session.
        payload: The user creation data.
        actor: The authenticated super_admin performing the action.

    Returns:
        PortalUser: The newly created portal user.

    Raises:
        HTTPException: 409 if the email address is already taken.
    """
    # Check for duplicate email before hashing the password (cheaper failure path)
    existing = await db.execute(select(PortalUser).where(PortalUser.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A portal user with this email already exists",
        )

    log.info("portal_user.creating", email=payload.email, role=payload.role)

    user = PortalUser(
        id=uuid.uuid4(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)

    await log_action(
        db=db,
        action=PORTAL_USER_CREATED,
        entity_type="portal_user",
        entity_id=str(user.id),
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        after_state={"email": user.email, "role": user.role},
    )

    await db.commit()
    await db.refresh(user)
    log.info("portal_user.created", user_id=str(user.id))
    return user


async def update_portal_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: PortalUserUpdate,
    actor: PortalUser,
) -> PortalUser:
    """
    Update a portal user's name or role and write an audit log row.

    Args:
        db: Active database session.
        user_id: The UUID of the user to update.
        payload: The fields to update (all optional).
        actor: The authenticated super_admin performing the action.

    Returns:
        PortalUser: The updated portal user.

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
        action=PORTAL_USER_CREATED,  # Re-using closest constant — update action not pre-defined
        entity_type="portal_user",
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


async def suspend_portal_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: PortalUser,
) -> PortalUser:
    """
    Suspend a portal user (set is_active = False) and write an audit log row.

    A super_admin cannot suspend themselves.

    Args:
        db: Active database session.
        user_id: The UUID of the user to suspend.
        actor: The authenticated super_admin performing the action.

    Returns:
        PortalUser: The suspended portal user.

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
        entity_type="portal_user",
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


async def activate_portal_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: PortalUser,
) -> PortalUser:
    """
    Activate a portal user (set is_active = True) and write an audit log row.

    Args:
        db: Active database session.
        user_id: The UUID of the user to activate.
        actor: The authenticated super_admin performing the action.

    Returns:
        PortalUser: The activated portal user.

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
        entity_type="portal_user",
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
