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
from app.models.brand import Brand
from app.models.group import Group
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


@dataclass
class ManagementAccess:
    """
    Holds the authenticated POS user and the scope context for a management
    portal session.

    Returned by resolve_management_access() and also produced by
    resolve_catalog_access() for management JWT callers.

    Scope rules:
      scope='site'  → site and brand are both populated
      scope='brand' → brand is populated; site is None
      scope='group' → group is populated; brand and site are None
    """

    user: POSUser
    access_profile: AccessProfile
    scope: str
    site: Site | None
    brand: Brand | None
    group: Group | None
    grant_id: uuid.UUID


@dataclass
class CatalogAccess:
    """
    Union access object accepted by catalog and report routes.

    Exactly one of pos_access, mgmt_access, or portal_access is set.
    Use the .brand_id property for brand-scoped queries; use .actor_user
    for audit logging.
    """

    pos_access: "POSAccess | None"
    mgmt_access: "ManagementAccess | None"
    portal_access: "PortalUser | None"

    @property
    def brand_id(self) -> uuid.UUID:
        """
        The brand_id in scope for this request.

        Raises ValueError for group-scope management access where no brand
        has been selected — routes that require a brand_id should use
        resolve_catalog_access_with_brand() instead.
        """
        if self.pos_access:
            return self.pos_access.user.brand_id
        if self.mgmt_access:
            if self.mgmt_access.brand:
                return self.mgmt_access.brand.id
            raise ValueError(
                "brand_id is not available for group-scope management access; "
                "the route must receive brand_id as a query/path parameter"
            )
        # portal_access has no brand_id by itself — caller must supply it
        raise ValueError(
            "brand_id is not available for portal admin access; "
            "the route must receive brand_id as a query/path parameter"
        )

    @property
    def actor_user(self) -> "POSUser | PortalUser":
        """The authenticated user, regardless of token type."""
        if self.pos_access:
            return self.pos_access.user
        if self.mgmt_access:
            return self.mgmt_access.user
        return self.portal_access  # type: ignore[return-value]

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


async def resolve_management_access(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> ManagementAccess:
    """
    Decode a management access JWT and resolve the user, grant, and scope context.

    Validates that:
    - The token is a valid signed mgmt_access JWT.
    - The POS user exists and is active.
    - The grant embedded in the token exists, is active, and belongs to this user.
    - The access profile on the grant has can_access_portal=True.
    - The scope entity (site, brand, or group) exists.

    Inject into management-only route handlers via:
        access: ManagementAccess = Depends(resolve_management_access)

    Args:
        credentials: Bearer token from the Authorization header.
        db: The active database session.

    Returns:
        ManagementAccess: Authenticated user, grant scope context, and entities.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or malformed.
        HTTPException: 403 if the user/grant is inactive, or profile lacks portal access.
    """
    try:
        payload = decode_token(credentials.credentials, expected_type="mgmt_access")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired management access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub", "")
    grant_id_str: str = payload.get("grant_id", "")
    scope: str = payload.get("scope", "")

    if not user_id_str or not grant_id_str or not scope:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed management token — missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
        grant_id = uuid.UUID(grant_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed management token — invalid UUID in claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the POS user
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

    # Validate the grant — must belong to this user and still be active
    grant_result = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.id == grant_id,
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access grant not found, revoked, or does not belong to this user",
        )

    # Validate the access profile still has portal access
    profile_result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.id == grant.access_profile_id,
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    access_profile = profile_result.scalar_one_or_none()
    if access_profile is None or not access_profile.can_access_portal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access profile does not permit portal login",
        )

    # Resolve scope entities
    resolved_site: Site | None = None
    resolved_brand: Brand | None = None
    resolved_group: Group | None = None

    if scope == "site" and grant.site_id:
        site_result = await db.execute(select(Site).where(Site.id == grant.site_id))
        resolved_site = site_result.scalar_one_or_none()
        if resolved_site and resolved_site.brand_id:
            brand_result = await db.execute(
                select(Brand).where(Brand.id == resolved_site.brand_id)
            )
            resolved_brand = brand_result.scalar_one_or_none()

    elif scope == "brand" and grant.brand_id:
        brand_result = await db.execute(select(Brand).where(Brand.id == grant.brand_id))
        resolved_brand = brand_result.scalar_one_or_none()

    elif scope == "group" and grant.group_id:
        group_result = await db.execute(select(Group).where(Group.id == grant.group_id))
        resolved_group = group_result.scalar_one_or_none()

    return ManagementAccess(
        user=user,
        access_profile=access_profile,
        scope=scope,
        site=resolved_site,
        brand=resolved_brand,
        group=resolved_group,
        grant_id=grant_id,
    )


async def resolve_catalog_access(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CatalogAccess:
    """
    Unified dependency for catalog and report routes.

    Accepts any of three token types (tried in order):
    1. portal JWT (type='access') — portal_user; full authority over any brand
    2. mgmt_access JWT — POS manager; scope-limited to their grant
    3. pos_access JWT — POS terminal user; site-scoped

    The result's .brand_id and .actor_user properties work identically for
    callers regardless of which token type was presented.

    Existing POS terminal routes that require site context should continue
    to use resolve_access() directly rather than this dependency, because
    resolve_catalog_access() does not guarantee a site is present.

    Args:
        credentials: Bearer token from the Authorization header.
        db: The active database session.

    Returns:
        CatalogAccess: Wraps whichever access type succeeded.

    Raises:
        HTTPException: 401 if no token type succeeds.
    """
    token_str = credentials.credentials

    # ── 1. Try portal JWT ────────────────────────────────────────────────────
    try:
        payload = decode_token(token_str, expected_type="access")
        user_id_str: str = payload.get("sub", "")
        portal_result = await db.execute(
            select(PortalUser).where(PortalUser.id == user_id_str)
        )
        portal_user = portal_result.scalar_one_or_none()
        if portal_user and portal_user.is_active:
            return CatalogAccess(pos_access=None, mgmt_access=None, portal_access=portal_user)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Portal user inactive")
    except JWTError:
        pass  # Not a portal token — try management

    # ── 2. Try management JWT ─────────────────────────────────────────────────
    try:
        payload = decode_token(token_str, expected_type="mgmt_access")
        # Re-use resolve_management_access logic inline to avoid double Depends() complexity
        user_id = uuid.UUID(payload.get("sub", ""))
        grant_id = uuid.UUID(payload.get("grant_id", ""))
        scope = payload.get("scope", "")

        user_r = await db.execute(select(POSUser).where(POSUser.id == user_id))
        pos_user = user_r.scalar_one_or_none()
        if not pos_user or not pos_user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="POS user inactive")

        grant_r = await db.execute(
            select(UserAccessGrant).where(
                UserAccessGrant.id == grant_id,
                UserAccessGrant.user_id == user_id,
                UserAccessGrant.is_active == True,  # noqa: E712
            )
        )
        grant = grant_r.scalar_one_or_none()
        if not grant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant revoked")

        prof_r = await db.execute(
            select(AccessProfile).where(
                AccessProfile.id == grant.access_profile_id,
                AccessProfile.can_access_portal == True,  # noqa: E712
                AccessProfile.is_active == True,  # noqa: E712
            )
        )
        access_profile = prof_r.scalar_one_or_none()
        if not access_profile:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Profile lacks portal access")

        resolved_site: Site | None = None
        resolved_brand: Brand | None = None
        resolved_group: Group | None = None

        if scope == "site" and grant.site_id:
            sr = await db.execute(select(Site).where(Site.id == grant.site_id))
            resolved_site = sr.scalar_one_or_none()
            if resolved_site:
                br = await db.execute(select(Brand).where(Brand.id == resolved_site.brand_id))
                resolved_brand = br.scalar_one_or_none()
        elif scope == "brand" and grant.brand_id:
            br = await db.execute(select(Brand).where(Brand.id == grant.brand_id))
            resolved_brand = br.scalar_one_or_none()
        elif scope == "group" and grant.group_id:
            gr = await db.execute(select(Group).where(Group.id == grant.group_id))
            resolved_group = gr.scalar_one_or_none()

        mgmt = ManagementAccess(
            user=pos_user,
            access_profile=access_profile,
            scope=scope,
            site=resolved_site,
            brand=resolved_brand,
            group=resolved_group,
            grant_id=grant_id,
        )
        return CatalogAccess(pos_access=None, mgmt_access=mgmt, portal_access=None)

    except (JWTError, ValueError):
        pass  # Not a management token — try POS

    # ── 3. Try POS access JWT ─────────────────────────────────────────────────
    try:
        payload = decode_token(token_str, expected_type="pos_access")
        user_id = uuid.UUID(payload.get("sub", ""))
        site_id = uuid.UUID(payload.get("site_id", ""))

        user_r = await db.execute(select(POSUser).where(POSUser.id == user_id))
        pos_user = user_r.scalar_one_or_none()
        if not pos_user or not pos_user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="POS user inactive")

        site_r = await db.execute(select(Site).where(Site.id == site_id))
        site = site_r.scalar_one_or_none()
        if not site:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Site not found")

        grant_r = await db.execute(
            select(UserAccessGrant).where(
                UserAccessGrant.user_id == user_id,
                UserAccessGrant.site_id == site_id,
                UserAccessGrant.is_active == True,  # noqa: E712
            )
        )
        grant = grant_r.scalar_one_or_none()
        if not grant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active grant for this site")

        prof_r = await db.execute(
            select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
        )
        access_profile = prof_r.scalar_one_or_none()
        if not access_profile:
            log.error(
                "resolve_catalog_access.profile_missing",
                grant_id=str(grant.id),
                access_profile_id=str(grant.access_profile_id),
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Access profile missing")

        pos_access = POSAccess(user=pos_user, site=site, access_profile=access_profile)
        return CatalogAccess(pos_access=pos_access, mgmt_access=None, portal_access=None)

    except JWTError:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
