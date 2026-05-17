"""Routes for POS user management — list, create, deactivate."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import USER_CREATED, USER_DEACTIVATED
from app.database import get_db
from app.models.pos_user import POSUser
from app.services.audit_service import log_action
from app.utils.dependencies import get_current_portal_user
from app.utils.security import hash_password

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/pos-users", tags=["pos-users"])


class PosUserOut(BaseModel):
    """POS user response schema."""

    id: str
    brand_id: str
    name: str
    email: str
    is_active: bool

    model_config = {"from_attributes": True}


class PosUserCreate(BaseModel):
    """Request body for creating a POS user."""

    brand_id: str
    name: str
    email: EmailStr
    password: str


@router.get("", response_model=list[PosUserOut])
async def list_pos_users(
    brand_id: str,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """List all POS users for a brand. Requires portal JWT."""
    result = await db.execute(
        select(POSUser)
        .where(POSUser.brand_id == brand_id)
        .offset(skip)
        .limit(limit)
        .order_by(POSUser.name)
    )
    return result.scalars().all()


@router.post("", response_model=PosUserOut, status_code=status.HTTP_201_CREATED)
async def create_pos_user(
    body: PosUserCreate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """Create a new POS user. Requires portal JWT."""
    # Check for duplicate email within the brand
    existing = await db.execute(
        select(POSUser).where(POSUser.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    user = POSUser(
        brand_id=body.brand_id,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_CREATED,
        entity_type="pos_user",
        entity_id=str(user.id),
        after_state={"name": user.name, "email": user.email, "brand_id": str(user.brand_id)},
    )

    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/deactivate", response_model=PosUserOut)
async def deactivate_pos_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """Deactivate a POS user. Requires portal JWT."""
    result = await db.execute(select(POSUser).where(POSUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_DEACTIVATED,
        entity_type="pos_user",
        entity_id=str(user.id),
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(user)
    return user
