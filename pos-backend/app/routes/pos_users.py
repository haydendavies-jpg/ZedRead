"""Routes for POS user management — list, create, edit, deactivate."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import USER_CREATED, USER_DEACTIVATED, USER_UPDATED
from app.database import get_db
from app.models.access_profile import AccessProfile
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.services.audit_service import log_action
from app.utils.dependencies import get_current_portal_user
from app.utils.security import hash_password

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/pos-users", tags=["pos-users"])


class SiteGrantSummary(BaseModel):
    """Minimal site grant info embedded in PosUserOut for the portal UI."""

    grant_id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    is_default: bool
    access_profile_name: str
    can_access_portal: bool


class PosUserOut(BaseModel):
    """POS user response schema — includes active site grants and portal access flag."""

    id: uuid.UUID
    ref: str
    brand_id: uuid.UUID
    name: str
    email: str
    is_active: bool
    # Active site-scope grants with grant ID, site info, and default flag
    site_grants: list[SiteGrantSummary] = []
    # True when at least one active grant uses a portal-capable access profile
    has_portal_access: bool = False

    model_config = {"from_attributes": True}


class PosUserCreate(BaseModel):
    """Request body for creating a POS user."""

    brand_id: str
    name: str
    email: EmailStr
    password: str


class PosUserUpdate(BaseModel):
    """Request body for editing a POS user — all fields optional."""

    name: str | None = None
    email: EmailStr | None = None


async def _attach_sites(
    db: AsyncSession,
    users: list[POSUser],
) -> list[PosUserOut]:
    """
    Fetch active site grants and portal access flag for a batch of users.

    Returns full SiteGrantSummary objects (including grant_id and is_default) so
    the portal UI can show the primary site and offer a "Set primary" action.

    Args:
        db: Active database session.
        users: List of POSUser ORM objects to enrich.

    Returns:
        list[PosUserOut]: Enriched user response objects.
    """
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Site grants — single joined query returning grant + site + profile info
    grants_q = (
        select(
            UserAccessGrant.user_id,
            UserAccessGrant.id,
            UserAccessGrant.site_id,
            UserAccessGrant.is_default,
            Site.name,
            AccessProfile.name,
            AccessProfile.can_access_portal,
        )
        .join(Site, UserAccessGrant.site_id == Site.id)
        .join(AccessProfile, UserAccessGrant.access_profile_id == AccessProfile.id)
        .where(
            UserAccessGrant.user_id.in_(user_ids),
            UserAccessGrant.scope == "site",
            UserAccessGrant.is_active.is_(True),
        )
        .order_by(UserAccessGrant.is_default.desc(), Site.name)
    )
    grants_result = await db.execute(grants_q)
    grants_by_user: dict[uuid.UUID, list[SiteGrantSummary]] = {}
    portal_users: set[uuid.UUID] = set()
    for (user_id, grant_id, site_id, is_default, site_name, profile_name, cap) in grants_result:
        grants_by_user.setdefault(user_id, []).append(
            SiteGrantSummary(
                grant_id=grant_id,
                site_id=site_id,
                site_name=site_name,
                is_default=is_default,
                access_profile_name=profile_name,
                can_access_portal=cap,
            )
        )
        if cap:
            portal_users.add(user_id)

    return [
        PosUserOut(
            id=u.id,
            ref=u.ref,
            brand_id=u.brand_id,
            name=u.name,
            email=u.email,
            is_active=u.is_active,
            site_grants=grants_by_user.get(u.id, []),
            has_portal_access=u.id in portal_users,
        )
        for u in users
    ]


@router.get("", response_model=list[PosUserOut])
async def list_pos_users(
    brand_id: str,
    site_id: str | None = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """List POS users for a brand, optionally filtered to those with a site grant."""
    q = select(POSUser).where(POSUser.brand_id == brand_id)

    if site_id:
        # Subquery: only users with an active site-scope grant for this site
        q = q.where(
            POSUser.id.in_(
                select(UserAccessGrant.user_id).where(
                    UserAccessGrant.site_id == site_id,
                    UserAccessGrant.is_active.is_(True),
                )
            )
        )

    q = q.offset(skip).limit(limit).order_by(POSUser.name)
    result = await db.execute(q)
    users = list(result.scalars().all())
    return await _attach_sites(db, users)


@router.post("", response_model=PosUserOut, status_code=status.HTTP_201_CREATED)
async def create_pos_user(
    body: PosUserCreate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """Create a new POS user. Requires portal JWT."""
    existing = await db.execute(select(POSUser).where(POSUser.email == body.email))
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
    return PosUserOut(
        id=user.id,
        ref=user.ref,
        brand_id=user.brand_id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        site_grants=[],
        has_portal_access=False,
    )


@router.patch("/{user_id}", response_model=PosUserOut)
async def update_pos_user(
    user_id: str,
    body: PosUserUpdate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_portal_user),
):
    """Edit a POS user's name and/or email. Requires portal JWT."""
    result = await db.execute(select(POSUser).where(POSUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    before: dict = {"name": user.name, "email": user.email}

    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        # Check for email conflict with another user
        dup = await db.execute(
            select(POSUser).where(POSUser.email == body.email, POSUser.id != user.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        user.email = body.email

    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_UPDATED,
        entity_type="pos_user",
        entity_id=str(user.id),
        before_state=before,
        after_state={"name": user.name, "email": user.email},
    )

    await db.commit()
    await db.refresh(user)
    result_list = await _attach_sites(db, [user])
    return result_list[0]


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
    result_list = await _attach_sites(db, [user])
    return result_list[0]
