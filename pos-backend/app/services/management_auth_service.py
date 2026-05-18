"""Business logic for unified portal login and management JWT issuance.

Extends the portal login flow to also accept POS user credentials. If the
email matches a portal_user, the existing portal JWT is issued. If it matches
a pos_user whose access profile has can_access_portal=True, a management JWT
is issued instead.
"""

import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCESS,
    AUTH_TOKEN_REFRESHED,
    MGMT_LOGIN_FAILED,
    MGMT_LOGIN_SUCCESS,
    MGMT_TOKEN_ISSUED,
)
from app.constants.statuses import ActorType, GrantScope
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.portal_user import PortalUser
from app.models.pos_user import POSUser
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.schemas.portal_auth import (
    GrantSummary,
    LoginRequest,
    ManagementTokenRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.services.audit_service import log_action
from app.utils.security import (
    create_access_token,
    create_mgmt_access_token,
    create_mgmt_refresh_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

log = structlog.get_logger(__name__)


async def _load_portal_user(db: AsyncSession, email: str) -> PortalUser | None:
    """Fetch a portal_user by email."""
    result = await db.execute(select(PortalUser).where(PortalUser.email == email))
    return result.scalar_one_or_none()


async def _load_pos_user(db: AsyncSession, email: str) -> POSUser | None:
    """Fetch a pos_user by email."""
    result = await db.execute(select(POSUser).where(POSUser.email == email))
    return result.scalar_one_or_none()


async def _portal_capable_grants(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[UserAccessGrant, AccessProfile]]:
    """
    Return all active grants for the user whose access profile allows portal login.

    Args:
        db: Active session.
        user_id: POS user UUID.

    Returns:
        list of (grant, profile) tuples.
    """
    result = await db.execute(
        select(UserAccessGrant, AccessProfile)
        .join(AccessProfile, UserAccessGrant.access_profile_id == AccessProfile.id)
        .where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.is_active == True,  # noqa: E712
            AccessProfile.can_access_portal == True,  # noqa: E712
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    return result.all()


async def _scope_name(
    db: AsyncSession,
    grant: UserAccessGrant,
) -> str:
    """
    Resolve a human-readable name for the grant's scope entity.

    Args:
        db: Active session.
        grant: The grant whose scope entity to name.

    Returns:
        str: The entity name (site, brand, or group name).
    """
    if grant.scope == GrantScope.SITE and grant.site_id:
        result = await db.execute(select(Site).where(Site.id == grant.site_id))
        site = result.scalar_one_or_none()
        return site.name if site else str(grant.site_id)

    if grant.scope == GrantScope.BRAND and grant.brand_id:
        result = await db.execute(select(Brand).where(Brand.id == grant.brand_id))
        brand = result.scalar_one_or_none()
        return brand.name if brand else str(grant.brand_id)

    if grant.scope == GrantScope.GROUP and grant.group_id:
        result = await db.execute(select(Group).where(Group.id == grant.group_id))
        group = result.scalar_one_or_none()
        return group.name if group else str(grant.group_id)

    return "Unknown"


def _build_mgmt_token(user: POSUser, grant: UserAccessGrant) -> tuple[str, str]:
    """
    Issue a management access + refresh token pair for the given grant.

    Args:
        user: The authenticated POS user.
        grant: The active grant to embed in the token.

    Returns:
        tuple[str, str]: (access_token, refresh_token).
    """
    access = create_mgmt_access_token(
        user_id=str(user.id),
        scope=grant.scope,
        grant_id=str(grant.id),
        site_id=str(grant.site_id) if grant.site_id else None,
        brand_id=str(grant.brand_id) if grant.brand_id else None,
        group_id=str(grant.group_id) if grant.group_id else None,
    )
    refresh = create_mgmt_refresh_token(str(user.id))
    return access, refresh


async def login(db: AsyncSession, payload: LoginRequest) -> UnifiedLoginResponse:
    """
    Unified portal login: try portal_users first, then pos_users.

    Portal user → issues portal access + refresh tokens (existing behaviour).
    POS user with one portal-capable grant → issues management JWT directly.
    POS user with multiple portal-capable grants → returns grant list for selection.
    Any failure → consistent 401 (no information about which table was checked).

    Args:
        db: Active database session.
        payload: Login credentials (email + password).

    Returns:
        UnifiedLoginResponse: Tokens or grant list depending on user type and grants.

    Raises:
        HTTPException: 401 for invalid credentials; 403 if no portal-capable grants.
    """
    log.info("auth.portal.login.attempt", email=payload.email)

    # ── 1. Try portal_user first ─────────────────────────────────────────────
    portal_user = await _load_portal_user(db, payload.email)
    if portal_user is not None:
        credentials_valid = (
            verify_password(payload.password, portal_user.password_hash)
            and portal_user.is_active
        )
        if not credentials_valid:
            await log_action(
                db=db,
                action=AUTH_LOGIN_FAILED,
                entity_type="portal_user",
                entity_id=str(portal_user.id),
                actor_type=ActorType.USER,
                actor_id=None,
                actor_email=payload.email,
                actor_name=None,
            )
            await db.commit()
            log.warning("auth.portal.login.failed", email=payload.email, reason="portal_user")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(str(portal_user.id), portal_user.role)
        refresh_token = create_refresh_token(str(portal_user.id))
        await log_action(
            db=db,
            action=AUTH_LOGIN_SUCCESS,
            entity_type="portal_user",
            entity_id=str(portal_user.id),
            actor_type=ActorType.USER,
            actor_id=portal_user.id,
            actor_email=portal_user.email,
            actor_name=portal_user.name,
        )
        await db.commit()
        log.info("auth.portal.login.success", user_id=str(portal_user.id))
        return UnifiedLoginResponse(access_token=access_token, refresh_token=refresh_token)

    # ── 2. Try pos_user ───────────────────────────────────────────────────────
    pos_user = await _load_pos_user(db, payload.email)
    pos_creds_valid = (
        pos_user is not None
        and verify_password(payload.password, pos_user.password_hash)
        and pos_user.is_active
    )

    if not pos_creds_valid:
        # Neither table matched — consistent 401 (never reveal which table was checked)
        entity_id = str(pos_user.id) if pos_user else payload.email
        await log_action(
            db=db,
            action=MGMT_LOGIN_FAILED,
            entity_type="pos_user",
            entity_id=entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
        )
        await db.commit()
        log.warning("auth.portal.login.failed", email=payload.email, reason="not_found_or_bad_pw")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load portal-capable grants for this pos_user
    grant_rows = await _portal_capable_grants(db, pos_user.id)
    if not grant_rows:
        await log_action(
            db=db,
            action=MGMT_LOGIN_FAILED,
            entity_type="pos_user",
            entity_id=str(pos_user.id),
            actor_type=ActorType.USER,
            actor_id=pos_user.id,
            actor_email=pos_user.email,
            actor_name=pos_user.name,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal-capable access grants for this account",
        )

    # Single grant → issue token immediately
    if len(grant_rows) == 1:
        grant, _ = grant_rows[0]
        access, refresh = _build_mgmt_token(pos_user, grant)
        await log_action(
            db=db,
            action=MGMT_LOGIN_SUCCESS,
            entity_type="pos_user",
            entity_id=str(pos_user.id),
            actor_type=ActorType.USER,
            actor_id=pos_user.id,
            actor_email=pos_user.email,
            actor_name=pos_user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.login.success", user_id=str(pos_user.id), scope=grant.scope)
        return UnifiedLoginResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=pos_user.id,
            user_name=pos_user.name,
        )

    # Multiple grants — check for a default grant and auto-issue if found
    default_grants = [(g, p) for g, p in grant_rows if g.is_default]
    if default_grants:
        grant, _ = default_grants[0]
        access, refresh = _build_mgmt_token(pos_user, grant)
        await log_action(
            db=db,
            action=MGMT_LOGIN_SUCCESS,
            entity_type="pos_user",
            entity_id=str(pos_user.id),
            actor_type=ActorType.USER,
            actor_id=pos_user.id,
            actor_email=pos_user.email,
            actor_name=pos_user.name,
        )
        await db.commit()
        log.info(
            "auth.portal.mgmt.login.success.default_grant",
            user_id=str(pos_user.id),
            scope=grant.scope,
        )
        return UnifiedLoginResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=pos_user.id,
            user_name=pos_user.name,
        )

    # No default set → return list for manual scope selection (no token yet)
    summaries: list[GrantSummary] = []
    for grant, profile in grant_rows:
        name = await _scope_name(db, grant)
        summaries.append(
            GrantSummary(
                grant_id=grant.id,
                scope=grant.scope,
                scope_name=name,
                access_profile_name=profile.name,
            )
        )

    log.info(
        "auth.portal.mgmt.login.scope_selection",
        user_id=str(pos_user.id),
        grant_count=len(summaries),
    )
    return UnifiedLoginResponse(
        user_id=pos_user.id,
        user_name=pos_user.name,
        available_grants=summaries,
    )


async def issue_management_token(
    db: AsyncSession,
    payload: ManagementTokenRequest,
) -> UnifiedLoginResponse:
    """
    Issue a management JWT for a specific grant after scope selection.

    Re-verifies the user's password to prevent grant enumeration by an attacker
    who intercepted the multi-grant login response.

    Args:
        db: Active database session.
        payload: user_id, grant_id, and password for re-verification.

    Returns:
        UnifiedLoginResponse: Management JWT pair with user info.

    Raises:
        HTTPException: 401 if credentials fail; 403 if grant is not portal-capable.
    """
    result = await db.execute(select(POSUser).where(POSUser.id == payload.user_id))
    pos_user = result.scalar_one_or_none()

    if pos_user is None or not verify_password(payload.password, pos_user.password_hash) or not pos_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load and validate the requested grant
    grant_result = await db.execute(
        select(UserAccessGrant)
        .where(
            UserAccessGrant.id == payload.grant_id,
            UserAccessGrant.user_id == payload.user_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_result.scalar_one_or_none()
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant not found or inactive",
        )

    profile_result = await db.execute(
        select(AccessProfile).where(
            AccessProfile.id == grant.access_profile_id,
            AccessProfile.can_access_portal == True,  # noqa: E712
            AccessProfile.is_active == True,  # noqa: E712
        )
    )
    if profile_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This access profile does not permit portal login",
        )

    access, refresh = _build_mgmt_token(pos_user, grant)

    await log_action(
        db=db,
        action=MGMT_TOKEN_ISSUED,
        entity_type="pos_user",
        entity_id=str(pos_user.id),
        actor_type=ActorType.USER,
        actor_id=pos_user.id,
        actor_email=pos_user.email,
        actor_name=pos_user.name,
    )
    await db.commit()

    log.info(
        "auth.portal.mgmt.token.issued",
        user_id=str(pos_user.id),
        grant_id=str(grant.id),
        scope=grant.scope,
    )
    return UnifiedLoginResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=pos_user.id,
        user_name=pos_user.name,
    )


async def refresh_management_token(
    db: AsyncSession, refresh_token: str
) -> UnifiedLoginResponse:
    """
    Exchange a valid management refresh token for a new management access + refresh pair.

    Re-reads the user's active grants to pick up any access changes since the
    last login. If the grant embedded in the expired access token is no longer
    valid, the caller must re-authenticate.

    Note: The refresh token carries only the user_id (no grant context). The
    caller must also supply grant_id to identify which session to renew.
    This endpoint simply validates the token and re-issues; the caller is
    responsible for passing grant_id via the ManagementTokenRequest flow if
    a full re-scope is needed.

    Args:
        db: Active database session.
        refresh_token: The management refresh JWT.

    Returns:
        UnifiedLoginResponse: New management token pair (no user_id populated
        since the grant context has not been re-resolved here).

    Raises:
        HTTPException: 401 if the token is invalid, expired, or the user is inactive.
    """
    from jose import JWTError  # local import avoids circular dependency at module level

    try:
        payload = decode_token(refresh_token, expected_type="mgmt_refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired management refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub", "")
    result = await db.execute(select(POSUser).where(POSUser.id == user_id_str))
    pos_user = result.scalar_one_or_none()

    if pos_user is None or not pos_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Re-issue as a single-grant token or return grant list if needed.
    # Since a refresh carries no grant_id, we check if the user still has
    # exactly one portal-capable grant; if multiple, they must re-select.
    grant_rows = await _portal_capable_grants(db, pos_user.id)
    if not grant_rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal-capable access grants remain for this account",
        )

    if len(grant_rows) == 1:
        grant, _ = grant_rows[0]
        new_access, new_refresh = _build_mgmt_token(pos_user, grant)
        await log_action(
            db=db,
            action=AUTH_TOKEN_REFRESHED,
            entity_type="pos_user",
            entity_id=str(pos_user.id),
            actor_type=ActorType.USER,
            actor_id=pos_user.id,
            actor_email=pos_user.email,
            actor_name=pos_user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.token.refreshed", user_id=str(pos_user.id))
        return UnifiedLoginResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user_id=pos_user.id,
            user_name=pos_user.name,
        )

    # Multiple grants — honour the default grant if set
    default_grants = [(g, p) for g, p in grant_rows if g.is_default]
    if default_grants:
        grant, _ = default_grants[0]
        new_access, new_refresh = _build_mgmt_token(pos_user, grant)
        await log_action(
            db=db,
            action=AUTH_TOKEN_REFRESHED,
            entity_type="pos_user",
            entity_id=str(pos_user.id),
            actor_type=ActorType.USER,
            actor_id=pos_user.id,
            actor_email=pos_user.email,
            actor_name=pos_user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.token.refreshed.default_grant", user_id=str(pos_user.id))
        return UnifiedLoginResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user_id=pos_user.id,
            user_name=pos_user.name,
        )

    # No default — caller must re-select via management-token
    summaries: list[GrantSummary] = []
    for grant, profile in grant_rows:
        name = await _scope_name(db, grant)
        summaries.append(
            GrantSummary(
                grant_id=grant.id,
                scope=grant.scope,
                scope_name=name,
                access_profile_name=profile.name,
            )
        )
    return UnifiedLoginResponse(
        user_id=pos_user.id,
        user_name=pos_user.name,
        available_grants=summaries,
    )
