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
from sqlalchemy import and_, false, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import outerjoin

from app.constants.statuses import SuperAdminRole
from app.database import get_db
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.pos_device import PosDevice
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pos_session import UserPOSSession
from app.utils.security import decode_token


@dataclass
class ImpersonatorSnapshot:
    """
    Carries the impersonating admin's identity (a User with superadmin_role
    set) during an impersonation session.

    Snapshotted from JWT claims at token-decode time so no extra DB query is
    needed per request. Used by _actor_from_mgmt() to attribute audit log
    rows to the admin, not the entity's master user.
    """

    id: uuid.UUID
    email: str
    name: str


@dataclass
class POSAccess:
    """
    Holds the authenticated POS user, their current site, and the access
    profile that governs what actions they may perform.

    Returned by resolve_access() and injected into POS route handlers.
    """

    user: User
    site: Site
    access_profile: AccessProfile
    device: PosDevice | None = None


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

    impersonator is set when a portal admin (a User with superadmin_role set)
    obtained this token via POST /admin/impersonate. All audit logs for the
    session must use the impersonator's id/email/name rather than the master
    user's.
    """

    user: User
    access_profile: AccessProfile
    scope: str
    site: Site | None
    brand: Brand | None
    group: Group | None
    grant_id: uuid.UUID
    impersonator: ImpersonatorSnapshot | None = None


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
    # A User with superadmin_role set, resolved from a portal (access-type) JWT
    portal_access: "User | None"

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
    def actor_user(self) -> "User | ImpersonatorSnapshot":
        """
        The effective actor for audit logging.

        During impersonation the admin is the actor, not the entity's master
        user — every audit row must carry the admin's id/email/name so the
        audit trail is attributable to the person who actually made the change.
        """
        if self.pos_access:
            return self.pos_access.user
        if self.mgmt_access:
            # Return impersonator snapshot so audit logging uses admin identity
            if self.mgmt_access.impersonator:
                return self.mgmt_access.impersonator
            return self.mgmt_access.user
        assert self.portal_access is not None  # one of the three must be set
        return self.portal_access

    def effective_brand_id(self, brand_id_param: "uuid.UUID | None" = None) -> uuid.UUID:
        """
        Resolve the effective brand_id for a catalog or report request.

        For POS and site/brand-scope management: brand_id comes from the token.
        For group-scope management and portal admin: brand_id must be supplied
        via the brand_id_param (a query parameter on the route).

        Args:
            brand_id_param: Optional brand_id from a query parameter.

        Returns:
            uuid.UUID: The resolved brand_id for this request.

        Raises:
            HTTPException: 422 if group/portal access is used without brand_id_param.
        """
        from fastapi import HTTPException, status  # local to avoid circular import

        if self.pos_access:
            return self.pos_access.user.brand_id
        if self.mgmt_access:
            if self.mgmt_access.brand:
                return self.mgmt_access.brand.id
            # group-scope: brand must come from query param
            if not brand_id_param:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="brand_id query parameter required for group-scope management access",
                )
            return brand_id_param
        # portal_access: brand must come from query param
        if not brand_id_param:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="brand_id query parameter required for portal admin access",
            )
        return brand_id_param

log = structlog.get_logger(__name__)

# Extracts the Bearer token from the Authorization header
_bearer = HTTPBearer()


async def _load_pos_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    site_id: uuid.UUID,
    jti: str,
    device_id: uuid.UUID | None,
) -> Row | None:
    """
    Load every entity a POS token resolution needs in ONE database round trip.

    Replaces what used to be five sequential queries (user, site, grant,
    profile, session). Each intermediate round trip costs a full network
    RTT to the database, which dominates request latency when the API and
    the database are deployed in different regions — auth alone accounted
    for most of the per-request delay before this consolidation.

    All joins are LEFT OUTER so a missing piece yields NULL columns rather
    than dropping the row — callers can then raise the exact same error
    (401 vs 403 vs 500) the old sequential checks produced.

    Args:
        db: The active database session.
        user_id: The ``sub`` claim from the decoded POS token.
        site_id: The ``site_id`` claim from the decoded POS token.
        jti: The ``jti`` claim (may be empty — the session column comes back NULL).
        device_id: The ``device_id`` claim, or None for a token with no device
            context (e.g. a PIN-verify switch that didn't supply device_token).

    Returns:
        Row | None: (User, Site, UserAccessGrant, AccessProfile, UserPOSSession,
            PosDevice) with NULLs for any piece that did not resolve, or None
            when the user itself does not exist.
    """
    # device_on joins on `false()` when the token carries no device_id, so the
    # PosDevice column comes back NULL rather than matching an unrelated row
    device_on = PosDevice.id == device_id if device_id is not None else false()

    # Explicit join chain (not method-chained .outerjoin on the select) — the
    # Site and UserPOSSession ON clauses reference only token claims, so
    # SQLAlchemy cannot infer their left side and needs it spelled out
    joins = (
        # Site is keyed by the token claim, not by the user — a single-row join
        outerjoin(User, Site, Site.id == site_id)
        .outerjoin(
            UserAccessGrant,
            and_(
                UserAccessGrant.user_id == User.id,
                UserAccessGrant.site_id == site_id,
                UserAccessGrant.is_active == True,  # noqa: E712
            ),
        )
        # Deliberately no is_active filter — mirrors the old sequential lookup,
        # which loaded the profile for POS access regardless of active state
        .outerjoin(AccessProfile, AccessProfile.id == UserAccessGrant.access_profile_id)
        .outerjoin(
            UserPOSSession,
            and_(
                UserPOSSession.token_jti == jti,
                UserPOSSession.ended_at.is_(None),  # active sessions only
            ),
        )
        .outerjoin(PosDevice, device_on)
    )
    stmt = (
        select(User, Site, UserAccessGrant, AccessProfile, UserPOSSession, PosDevice)
        .select_from(joins)
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    return result.first()


async def _load_mgmt_context(
    db: AsyncSession, user_id: uuid.UUID, grant_id: uuid.UUID, scope: str
) -> Row | None:
    """
    Load every entity a management token resolution needs in ONE round trip.

    Replaces what used to be up to six sequential queries (user, grant,
    profile, then scope entities). See _load_pos_context for why round trips
    matter: each one costs a full network RTT to the database.

    The scope-entity joins are built from the token's ``scope`` claim so the
    query resolves exactly what the old per-scope branches resolved:
      scope='site'  → Site from grant.site_id, Brand from site.brand_id
      scope='brand' → Brand from grant.brand_id
      scope='group' → Group from grant.group_id

    Args:
        db: The active database session.
        user_id: The ``sub`` claim from the decoded management token.
        grant_id: The ``grant_id`` claim from the decoded management token.
        scope: The ``scope`` claim ('site' | 'brand' | 'group').

    Returns:
        Row | None: (User, UserAccessGrant, AccessProfile, Site, Brand, Group)
            with NULLs for any piece that did not resolve, or None when the
            user itself does not exist.
    """
    # Scope-gated join conditions: LEFT JOIN ... ON false yields NULL columns
    # for entities outside the token's scope, keeping the row single and flat
    site_on = Site.id == UserAccessGrant.site_id if scope == "site" else false()
    if scope == "site":
        brand_on = Brand.id == Site.brand_id  # brand comes via the site
    elif scope == "brand":
        brand_on = Brand.id == UserAccessGrant.brand_id
    else:
        brand_on = false()
    group_on = Group.id == UserAccessGrant.group_id if scope == "group" else false()

    # Explicit join chain — the scope-gated ON clauses (LEFT JOIN ... ON false)
    # reference no prior entity, so the left side must be spelled out
    joins = (
        outerjoin(
            User,
            UserAccessGrant,
            and_(
                UserAccessGrant.id == grant_id,
                UserAccessGrant.user_id == User.id,
                UserAccessGrant.is_active == True,  # noqa: E712
            ),
        )
        .outerjoin(
            AccessProfile,
            and_(
                AccessProfile.id == UserAccessGrant.access_profile_id,
                AccessProfile.is_active == True,  # noqa: E712
            ),
        )
        .outerjoin(Site, site_on)
        .outerjoin(Brand, brand_on)
        .outerjoin(Group, group_on)
    )
    stmt = (
        select(User, UserAccessGrant, AccessProfile, Site, Brand, Group)
        .select_from(joins)
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    return result.first()


def _check_pos_session_row(jti: str, session: UserPOSSession | None) -> None:
    """
    Verify the POS token's session has not been revoked (logged out).

    Every POS access token carries a ``jti`` that matches a ``user_pos_sessions``
    row written at login/PIN-verify time. Logout sets ``ended_at`` on that row;
    this check rejects any token whose session is missing or already ended, which
    is what makes POS tokens revocable before their natural expiry. The row
    itself is fetched as part of _load_pos_context's single query.

    Args:
        jti: The ``jti`` claim from the decoded POS token.
        session: The active UserPOSSession joined for that jti, or None.

    Raises:
        HTTPException: 401 if the jti is absent, unknown, or its session ended.
    """
    if not jti:
        # Older tokens minted before revocation existed carried a jti too, so a
        # missing jti means a malformed/forged token — reject it.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed POS token — missing session id",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="POS session has ended — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _actor_from_mgmt(mgmt: ManagementAccess) -> dict:
    """
    Return audit-log actor kwargs for a management-portal request.

    During impersonation the admin is the effective actor; otherwise the
    entity's master user is. Call as ``**_actor_from_mgmt(mgmt)`` inside
    log_action() to attribute the row to the correct identity.

    Args:
        mgmt: The resolved ManagementAccess for the current request.

    Returns:
        dict: Keys actor_id, actor_email, actor_name ready for log_action().
    """
    if mgmt.impersonator:
        return {
            "actor_id": mgmt.impersonator.id,
            "actor_email": mgmt.impersonator.email,
            "actor_name": mgmt.impersonator.name,
            "impersonator_id": mgmt.impersonator.id,
            "impersonator_email": mgmt.impersonator.email,
        }
    return {
        "actor_id": mgmt.user.id,
        "actor_email": mgmt.user.email,
        "actor_name": mgmt.user.name,
    }


async def get_current_superadmin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the Bearer access token and return the authenticated portal admin.

    Raises HTTP 401 for invalid/expired tokens and HTTP 403 for inactive users.

    Args:
        credentials: The HTTP Bearer credentials extracted from the Authorization header.
        db: The active database session.

    Returns:
        User: The authenticated and active User row (superadmin_role set).

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
        select(User).where(User.id == user_id, User.superadmin_role.isnot(None))
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

    # Reject tokens minted before a token_version bump (password change/logout)
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_super_admin(
    current_user: User = Depends(get_current_superadmin),
) -> User:
    """
    Dependency that restricts a route to Admin-role SuperAdmins only.

    Args:
        current_user: The authenticated portal admin from get_current_superadmin.

    Returns:
        User: The authenticated Admin-role portal admin.

    Raises:
        HTTPException: 403 if the user is not an Admin-role portal admin.
    """
    if current_user.superadmin_role != SuperAdminRole.ADMIN.value:
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

    device_id_str: str | None = payload.get("device_id") or None

    try:
        user_id = uuid.UUID(user_id_str)
        site_id = uuid.UUID(site_id_str)
        device_id = uuid.UUID(device_id_str) if device_id_str else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed POS token — invalid UUID in claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # One round trip loads user, site, grant, profile, session, and device
    # together; the checks below preserve the old sequential error order
    row = await _load_pos_context(db, user_id, site_id, payload.get("jti", ""), device_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="POS user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, site, grant, access_profile, pos_session, device = row
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="POS user account is inactive",
        )

    if site is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Site from token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

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

    # Reject tokens whose session has been revoked via logout
    _check_pos_session_row(payload.get("jti", ""), pos_session)

    return POSAccess(user=user, site=site, access_profile=access_profile, device=device)


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
    imp_id_str: str | None = payload.get("imp_id")
    imp_email: str = payload.get("imp_email", "")
    imp_name: str = payload.get("imp_name", "")

    if not user_id_str or not grant_id_str or not scope:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed management token — missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
        grant_id = uuid.UUID(grant_id_str)
        impersonator: ImpersonatorSnapshot | None = (
            ImpersonatorSnapshot(id=uuid.UUID(imp_id_str), email=imp_email, name=imp_name)
            if imp_id_str else None
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed management token — invalid UUID in claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # One round trip loads user, grant, profile, and scope entities together;
    # the checks below preserve the old sequential error order and messages
    row = await _load_mgmt_context(db, user_id, grant_id, scope)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="POS user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, grant, access_profile, resolved_site, resolved_brand, resolved_group = row
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="POS user account is inactive",
        )

    # Reject tokens minted before a token_version bump (logout-everywhere)
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access grant not found, revoked, or does not belong to this user",
        )

    # Portal access is gated on backend_role per grant, not access profile flag
    if not grant.backend_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This grant does not have backend access configured",
        )

    if access_profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access profile not found or inactive",
        )

    return ManagementAccess(
        user=user,
        access_profile=access_profile,
        scope=scope,
        site=resolved_site,
        brand=resolved_brand,
        group=resolved_group,
        grant_id=grant_id,
        impersonator=impersonator,
    )


async def resolve_catalog_access(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> CatalogAccess:
    """
    Unified dependency for catalog and report routes.

    Accepts any of three token types (tried in order):
    1. portal JWT (type='access') — superadmin; full authority over any brand
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
            select(User).where(User.id == user_id_str, User.superadmin_role.isnot(None))
        )
        superadmin = portal_result.scalar_one_or_none()
        if superadmin and superadmin.is_active:
            return CatalogAccess(pos_access=None, mgmt_access=None, portal_access=superadmin)
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
        _imp_id = payload.get("imp_id")
        _catalog_impersonator: ImpersonatorSnapshot | None = (
            ImpersonatorSnapshot(
                id=uuid.UUID(_imp_id),
                email=payload.get("imp_email", ""),
                name=payload.get("imp_name", ""),
            )
            if _imp_id else None
        )

        # One round trip loads user, grant, profile, and scope entities together
        row = await _load_mgmt_context(db, user_id, grant_id, scope)
        user = row.User if row is not None else None
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="POS user inactive")

        # Reject tokens minted before a token_version bump (logout-everywhere)
        if payload.get("tv", 0) != user.token_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked — please log in again",
                headers={"WWW-Authenticate": "Bearer"},
            )

        grant = row.UserAccessGrant
        if not grant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant revoked")

        # Portal access is gated on backend_role per grant, not access profile flag
        if not grant.backend_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Grant does not have backend access configured")

        access_profile = row.AccessProfile
        if not access_profile:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access profile not found or inactive")

        mgmt = ManagementAccess(
            user=user,
            access_profile=access_profile,
            scope=scope,
            site=row.Site,
            brand=row.Brand,
            group=row.Group,
            grant_id=grant_id,
            impersonator=_catalog_impersonator,
        )
        return CatalogAccess(pos_access=None, mgmt_access=mgmt, portal_access=None)

    except (JWTError, ValueError):
        pass  # Not a management token — try POS

    # ── 3. Try POS access JWT ─────────────────────────────────────────────────
    try:
        payload = decode_token(token_str, expected_type="pos_access")
        user_id = uuid.UUID(payload.get("sub", ""))
        site_id = uuid.UUID(payload.get("site_id", ""))
        device_id_str = payload.get("device_id") or None
        device_id = uuid.UUID(device_id_str) if device_id_str else None

        # One round trip loads user, site, grant, profile, session, and device
        row = await _load_pos_context(db, user_id, site_id, payload.get("jti", ""), device_id)
        user = row.User if row is not None else None
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="POS user inactive")

        site = row.Site
        if not site:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Site not found")

        grant = row.UserAccessGrant
        if not grant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active grant for this site")

        access_profile = row.AccessProfile
        if not access_profile:
            log.error(
                "resolve_catalog_access.profile_missing",
                grant_id=str(grant.id),
                access_profile_id=str(grant.access_profile_id),
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Access profile missing")

        # Reject tokens whose session has been revoked via logout
        _check_pos_session_row(payload.get("jti", ""), row.UserPOSSession)

        pos_access = POSAccess(user=user, site=site, access_profile=access_profile, device=row.PosDevice)
        return CatalogAccess(pos_access=pos_access, mgmt_access=None, portal_access=None)

    except JWTError:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
