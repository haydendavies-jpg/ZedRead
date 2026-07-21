"""Admin impersonation endpoint — lets a portal admin session into any entity's management portal.

All actions taken during the impersonation session are logged under the admin's
identity (actor_id/email/name carry the admin's details), not the master user's,
so the audit trail is always attributable to the human who made the change.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import ADMIN_IMPERSONATION_STARTED
from app.constants.statuses import ActorType
from app.database import get_db
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.services.audit_service import log_action
from app.services.management_auth_service import resolve_grant_brand_id
from app.utils.dependencies import require_super_admin
from app.utils.security import create_impersonation_token

router = APIRouter(prefix="/admin", tags=["admin"])


class MasterGrantResponse(BaseModel):
    """Grant ID of an entity's master user — used by the portal to initiate impersonation."""

    grant_id: uuid.UUID


class ImpersonateRequest(BaseModel):
    """Payload for POST /admin/impersonate."""

    grant_id: uuid.UUID


class ImpersonateResponse(BaseModel):
    """Token response for a successful impersonation request."""

    access_token: str
    token_type: str = "bearer"


@router.get("/master-grant", response_model=MasterGrantResponse, status_code=status.HTTP_200_OK)
async def get_master_grant(
    site_id: uuid.UUID | None = Query(None, description="Site ID"),
    brand_id: uuid.UUID | None = Query(None, description="Brand ID"),
    group_id: uuid.UUID | None = Query(None, description="Group ID"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> MasterGrantResponse:
    """
    Return the active grant ID for an entity's master user.

    Exactly one of site_id, brand_id, or group_id must be supplied.
    The grant is used by the portal to initiate impersonation via POST /admin/impersonate.

    Args:
        site_id: Resolve the master grant for this site.
        brand_id: Resolve the master grant for this brand.
        group_id: Resolve the master grant for this group.
        db: Active database session.
        admin: The authenticated Admin-role portal admin.

    Returns:
        MasterGrantResponse: The active grant ID for the entity's master user.

    Raises:
        HTTPException: 400 if none or more than one entity ID is supplied.
        HTTPException: 404 if no active master grant is found for the entity.
    """
    supplied = sum(x is not None for x in (site_id, brand_id, group_id))
    if supplied != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of site_id, brand_id, or group_id must be supplied",
        )

    q = (
        select(UserAccessGrant)
        .join(User, User.id == UserAccessGrant.user_id)
        .where(
            UserAccessGrant.is_active == True,  # noqa: E712
            User.is_master_user == True,  # noqa: E712
        )
    )
    if site_id is not None:
        q = q.where(UserAccessGrant.site_id == site_id)
    elif brand_id is not None:
        q = q.where(UserAccessGrant.brand_id == brand_id)
    else:
        q = q.where(UserAccessGrant.group_id == group_id)

    result = await db.execute(q)
    grant = result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active master grant found for this entity",
        )

    return MasterGrantResponse(grant_id=grant.id)


@router.post("/impersonate", response_model=ImpersonateResponse, status_code=status.HTTP_200_OK)
async def impersonate(
    body: ImpersonateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> ImpersonateResponse:
    """
    Issue a management-portal JWT that impersonates an entity's master user.

    The returned token is a standard mgmt_access JWT with three extra claims
    (imp_id, imp_email, imp_name) that resolve_management_access() uses to
    attribute every audit row to the admin rather than the master user.

    The portal opens this token in a new tab under /management, where the
    ImpersonationBanner component reads the imp_name claim to display:
    'Viewing as [Entity Name] — actions logged as [Admin Name]'.

    Args:
        body: Contains the grant_id for the entity to impersonate.
        admin: The authenticated Admin-role portal admin.

    Returns:
        ImpersonateResponse: A management access JWT ready for use.

    Raises:
        HTTPException: 404 if the grant does not exist or is not active.
        HTTPException: 403 if the grant's user is not a master user (prevents
            admins from impersonating arbitrary non-master accounts).
    """
    # Load the grant — must be active
    grant_r = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.id == body.grant_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_r.scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grant not found or inactive",
        )

    # Load the grant's owner — must be a master user
    user_r = await db.execute(select(User).where(User.id == grant.user_id))
    master_user = user_r.scalar_one_or_none()
    if master_user is None or not master_user.is_master_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Impersonation is only allowed for entity master users",
        )

    token = create_impersonation_token(
        user_id=str(master_user.id),
        scope=grant.scope,
        grant_id=str(grant.id),
        site_id=str(grant.site_id) if grant.site_id else None,
        # Site-scope grants store no brand_id — derived from the Site row so the
        # portal's brand-scoped catalog pages work inside a site session
        brand_id=await resolve_grant_brand_id(db, grant),
        group_id=str(grant.group_id) if grant.group_id else None,
        admin_id=str(admin.id),
        admin_email=admin.email,
        admin_name=admin.name,
        token_version=master_user.token_version,
    )

    await log_action(
        db=db,
        action=ADMIN_IMPERSONATION_STARTED,
        entity_type="user_access_grant",
        entity_id=str(grant.id),
        actor_type=ActorType.USER,
        actor_id=admin.id,
        actor_email=admin.email,
        actor_name=admin.name,
        after_state={
            "grant_id": str(grant.id),
            "scope": grant.scope,
            "master_user_id": str(master_user.id),
        },
    )
    await db.commit()

    return ImpersonateResponse(access_token=token)
