"""FastAPI dependency functions for authentication and authorisation.

Import these into route handlers via Depends() rather than re-implementing
the auth logic in route files.
"""

import uuid
from dataclasses import dataclass

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.statuses import PortalUserRole
from app.database import get_db
from app.models.access_profile import AccessProfile
from app.models.portal_user import PortalUser
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.utils.security import decode_token


@dataclass
class POSAccess:
    """
    Holds the authenticated POS user, their current site, and the access
    profile that governs what actions they may perform.

    Returned by resolve_access() and injected into POS route handlers.
    """

    user: POSUser
    site: Site
    access_profile: AccessProfile

log = structlog.get_logger(__name__)

# Extracts the Bearer token from the Authorization header
_bearer = HTTPBearer()


async def get_current_portal_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> PortalUser:
    """
    Decode the Bearer access token and return the authenticated portal user.

    Raises HTTP 401 for invalid/expired tokens and HTTP 403 for inactive users.

    Args:
        credentials: The HTTP Bearer credentials extracted from the Authorization header.
        db: The active database session.

    Returns:
        PortalUser: The authenticated and active portal user.

    Raises:
        HTTPException: 401 if the token is invalid or expired.
        HTTPException: 403 if the user account is inactive.
    """
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub", "")
    result = await db.execute(
        select(PortalUser).where(PortalUser.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return user


def require_super_admin(
    current_user: PortalUser = Depends(get_current_portal_user),
) -> PortalUser:
    """
    Dependency that restricts a route to super_admin users only.

    Args:
        current_user: The authenticated portal user from get_current_portal_user.

    Returns:
        PortalUser: The authenticated super_admin user.

    Raises:
        HTTPException: 403 if the user is not a super_admin.
    """
    if current_user.role != PortalUserRole.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


async def resolve_access(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> POSAccess:
    """
    Decode a POS access JWT and resolve the user, site, and access profile.

    Validates that:
    - The token is a valid signed pos_access JWT.
    - The POS user exists and is active.
    - The site embedded in the token exists.
    - The user has an active UserAccessGrant for that site.

    Inject into POS route handlers via ``access: POSAccess = Depends(resolve_access)``.

    Args:
        credentials: Bearer token from the Authorization header.
        db: The active database session.

    Returns:
        POSAccess: Authenticated user, site, and access profile.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or malformed.
        HTTPException: 403 if the user is inactive or has no grant for this site.
    """
    try:
        payload = decode_token(credentials.credentials, expected_type="pos_access")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired POS access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub", "")
    site_id_str: str = payload.get("site_id", "")

    if not user_id_str or not site_id_str:
        # Token is missing required claims — treat as invalid
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed POS token — missing sub or site_id claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
        site_id = uuid.UUID(site_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed POS token — invalid UUID in claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch and validate the POS user
    user_result = await db.execute(select(POSUser).where(POSUser.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="POS user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="POS user account is inactive",
        )

    # Fetch the site
    site_result = await db.execute(select(Site).where(Site.id == site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Site from token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the user has an active grant for this site and load the profile
    grant_result = await db.execute(
        select(UserAccessGrant)
        .where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.site_id == site_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

    # Load the access profile for this grant
    profile_result = await db.execute(
        select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
    )
    access_profile = profile_result.scalar_one_or_none()
    if access_profile is None:
        # Should never happen due to FK constraints — log and treat as server error
        log.error(
            "resolve_access.profile_missing",
            grant_id=str(grant.id),
            access_profile_id=str(grant.access_profile_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Access profile not found for grant",
        )

    return POSAccess(user=user, site=site, access_profile=access_profile)
