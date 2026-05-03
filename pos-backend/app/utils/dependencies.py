"""FastAPI dependency functions for authentication and authorisation.

Import these into route handlers via Depends() rather than re-implementing
the auth logic in route files.
"""

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.statuses import PortalUserRole
from app.database import get_db
from app.models.portal_user import PortalUser
from app.utils.security import decode_token

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
