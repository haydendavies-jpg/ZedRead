"""Business logic for unified portal login and management JWT issuance.

Extends the portal login flow to also accept POS user credentials. Portal
access for a User is gated on backend_role (per-grant), not on the POS
access profile. If an email matches only a superadmin, the portal JWT is
issued; if it matches only a portal-capable user, a management JWT is
issued (directly, via default grant, or via grant selection). If an email
matches both a superadmin and a portal-capable user, the caller is shown
both identities (ROLE_MODEL.md §3) and must select one via
POST /auth/portal/identity-token before either token type is issued.
"""

import os
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
from app.models.superadmin import SuperAdmin
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.schemas.portal_auth import (
    GrantSummary,
    IdentitySummary,
    IdentityTokenRequest,
    LoginRequest,
    ManagementTokenRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.services.audit_service import log_action
from app.utils.rate_limit import check_rate_limit
from app.utils.security import (
    create_access_token,
    create_mgmt_access_token,
    create_mgmt_refresh_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

log = structlog.get_logger(__name__)

# Login throttle: at most _LOGIN_MAX_ATTEMPTS per account per window
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))


async def _load_superadmin(db: AsyncSession, email: str) -> SuperAdmin | None:
    """Fetch a superadmin by email."""
    result = await db.execute(select(SuperAdmin).where(SuperAdmin.email == email))
    return result.scalar_one_or_none()


async def _load_users(db: AsyncSession, email: str) -> list[User]:
    """Fetch all users with the given email (multiple allowed — same person can manage several entities)."""
    result = await db.execute(select(User).where(User.email == email))
    return list(result.scalars().all())


async def _portal_capable_grants(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserAccessGrant]:
    """
    Return all active grants for the user that have a backend_role set.

    Portal login is gated on backend_role (per-grant) rather than on the
    POS access profile's can_access_portal flag, so a POS user can have
    backend access at any scope independently of their POS role tier.

    Args:
        db: Active session.
        user_id: POS user UUID.

    Returns:
        list[UserAccessGrant]: Grants with a non-null backend_role.
    """
    result = await db.execute(
        select(UserAccessGrant)
        .where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.is_active == True,  # noqa: E712
            UserAccessGrant.backend_role.isnot(None),
        )
    )
    return list(result.scalars().all())


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


async def resolve_grant_brand_id(db: AsyncSession, grant: UserAccessGrant) -> str | None:
    """
    Resolve the brand_id claim to embed in a management token for a grant.

    Site-scope grants store only site_id (brand_id is NULL on the grant row),
    but the portal relies on the token's brand_id claim to drive brand-scoped
    catalog pages — so derive it from the Site row for site-scope grants.

    Args:
        db: Active database session.
        grant: The grant whose brand context to resolve.

    Returns:
        str | None: The brand UUID string, or None for group-scope grants.
    """
    if grant.brand_id:
        return str(grant.brand_id)
    if grant.scope == GrantScope.SITE and grant.site_id:
        result = await db.execute(select(Site.brand_id).where(Site.id == grant.site_id))
        brand_id = result.scalar_one_or_none()
        return str(brand_id) if brand_id else None
    return None


async def _build_mgmt_token(db: AsyncSession, user: User, grant: UserAccessGrant) -> tuple[str, str]:
    """
    Issue a management access + refresh token pair for the given grant.

    Args:
        db: Active database session (needed to derive brand_id for site-scope grants).
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
        brand_id=await resolve_grant_brand_id(db, grant),
        group_id=str(grant.group_id) if grant.group_id else None,
        token_version=user.token_version,
    )
    refresh = create_mgmt_refresh_token(str(user.id), user.token_version)
    return access, refresh


async def _issue_superadmin_tokens(db: AsyncSession, superadmin: SuperAdmin) -> UnifiedLoginResponse:
    """
    Issue portal access + refresh tokens for an authenticated superadmin.

    Writes the AUTH_LOGIN_SUCCESS audit row and commits the transaction.

    Args:
        db: Active database session.
        superadmin: The authenticated superadmin.

    Returns:
        UnifiedLoginResponse: Portal token pair, no user_id/grant fields.
    """
    access_token = create_access_token(str(superadmin.id), superadmin.role, superadmin.token_version)
    refresh_token = create_refresh_token(str(superadmin.id), superadmin.token_version)
    await log_action(
        db=db,
        action=AUTH_LOGIN_SUCCESS,
        entity_type="superadmin",
        entity_id=str(superadmin.id),
        actor_type=ActorType.USER,
        actor_id=superadmin.id,
        actor_email=superadmin.email,
        actor_name=superadmin.name,
    )
    await db.commit()
    log.info("auth.portal.login.success", user_id=str(superadmin.id))
    return UnifiedLoginResponse(access_token=access_token, refresh_token=refresh_token)


async def _resolve_user_login(db: AsyncSession, user: User) -> UnifiedLoginResponse:
    """
    Resolve a portal-capable user's login into tokens or a grant-selection list.

    Single grant or a grant marked is_default → issues a management token
    directly. Multiple grants with no default → returns available_grants
    for the caller to select via POST /auth/portal/management-token.

    Args:
        db: Active database session.
        user: The authenticated, portal-capable user (caller has already
            verified credentials and that at least one portal-capable
            grant exists).

    Returns:
        UnifiedLoginResponse: Management tokens, or a grant list for selection.
    """
    grant_rows = await _portal_capable_grants(db, user.id)

    # Single grant → issue token immediately
    if len(grant_rows) == 1:
        grant = grant_rows[0]
        access, refresh = await _build_mgmt_token(db, user, grant)
        await log_action(
            db=db,
            action=MGMT_LOGIN_SUCCESS,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.login.success", user_id=str(user.id), scope=grant.scope)
        return UnifiedLoginResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=user.id,
            user_name=user.name,
        )

    # Multiple grants — check for a default grant and auto-issue if found
    default_grants = [g for g in grant_rows if g.is_default]
    if default_grants:
        grant = default_grants[0]
        access, refresh = await _build_mgmt_token(db, user, grant)
        await log_action(
            db=db,
            action=MGMT_LOGIN_SUCCESS,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
        )
        await db.commit()
        log.info(
            "auth.portal.mgmt.login.success.default_grant",
            user_id=str(user.id),
            scope=grant.scope,
        )
        return UnifiedLoginResponse(
            access_token=access,
            refresh_token=refresh,
            user_id=user.id,
            user_name=user.name,
        )

    # No default set → return list for manual scope selection (no token yet)
    summaries: list[GrantSummary] = []
    for grant in grant_rows:
        name = await _scope_name(db, grant)
        prof_r = await db.execute(
            select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
        )
        profile = prof_r.scalar_one_or_none()
        summaries.append(
            GrantSummary(
                user_id=user.id,
                grant_id=grant.id,
                scope=grant.scope,
                scope_name=name,
                access_profile_name=profile.name if profile else "",
            )
        )

    log.info(
        "auth.portal.mgmt.login.scope_selection",
        user_id=str(user.id),
        grant_count=len(summaries),
    )
    return UnifiedLoginResponse(
        user_id=user.id,
        user_name=user.name,
        available_grants=summaries,
    )


async def login(db: AsyncSession, payload: LoginRequest) -> UnifiedLoginResponse:
    """
    Unified portal login, disambiguating across superadmins and users.

    Loads both a candidate superadmin and a candidate user by email. If both
    have valid credentials (the user additionally needing at least one
    portal-capable grant), neither token is issued yet — instead the caller
    is shown both identities (ROLE_MODEL.md §3) and must call
    POST /auth/portal/identity-token with the chosen identity_type. If only
    one candidate is valid, behaviour is unchanged from before disambiguation
    existed: superadmin → portal tokens; user → management tokens or a grant
    list for selection. If neither is valid → consistent 401 (no information
    about which table was checked).

    Args:
        db: Active database session.
        payload: Login credentials (email + password).

    Returns:
        UnifiedLoginResponse: Tokens, a grant list, or an identity list,
        depending on what matches the supplied email.

    Raises:
        HTTPException: 401 for invalid credentials; 403 if a user matches
            but has no portal-capable grants.
    """
    log.info("auth.portal.login.attempt", email=payload.email)

    # Throttle repeated attempts against a single account before doing any
    # credential work — mitigates password brute-forcing (review finding S3).
    check_rate_limit(
        f"portal_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    superadmin = await _load_superadmin(db, payload.email)
    superadmin_valid = (
        superadmin is not None
        and verify_password(payload.password, superadmin.password_hash)
        and superadmin.is_active
    )

    # Support shared emails — same operator may have master-user accounts at multiple entities.
    # Collect all users with this email, validate each independently, merge their grants.
    all_users = await _load_users(db, payload.email)
    authenticated_user_grants: list[tuple[User, list[UserAccessGrant]]] = []
    any_user_creds_valid = False
    for candidate in all_users:
        if not candidate.is_active or not verify_password(payload.password, candidate.password_hash):
            continue
        any_user_creds_valid = True
        grants = await _portal_capable_grants(db, candidate.id)
        if grants:
            authenticated_user_grants.append((candidate, grants))
    user_valid = bool(authenticated_user_grants)

    # ── Both identities valid for this email → disambiguate, issue no tokens yet ──
    if superadmin_valid and user_valid:
        log.info("auth.portal.login.identity_selection", email=payload.email)
        first_user = authenticated_user_grants[0][0]
        return UnifiedLoginResponse(
            available_identities=[
                IdentitySummary(identity_type="superadmin", display_name=superadmin.name),
                IdentitySummary(identity_type="user", display_name=first_user.name),
            ]
        )

    # ── Only superadmin valid ────────────────────────────────────────────
    if superadmin_valid:
        return await _issue_superadmin_tokens(db, superadmin)

    # ── One or more users valid with grants ──────────────────────────────
    if user_valid:
        # Flatten all (user, grant) pairs across all authenticated users
        flat: list[tuple[User, UserAccessGrant]] = [
            (u, g) for u, grants in authenticated_user_grants for g in grants
        ]
        if len(flat) == 1:
            user, grant = flat[0]
            access, refresh = await _build_mgmt_token(db, user, grant)
            await log_action(
                db=db,
                action=MGMT_LOGIN_SUCCESS,
                entity_type="user",
                entity_id=str(user.id),
                actor_type=ActorType.USER,
                actor_id=user.id,
                actor_email=user.email,
                actor_name=user.name,
            )
            await db.commit()
            log.info("auth.portal.mgmt.login.success", user_id=str(user.id), scope=grant.scope)
            return UnifiedLoginResponse(
                access_token=access,
                refresh_token=refresh,
                user_id=user.id,
                user_name=user.name,
            )

        # Multiple grants across one or more users → show picker; caller selects via management-token
        summaries: list[GrantSummary] = []
        for u, g in flat:
            name = await _scope_name(db, g)
            prof_r = await db.execute(
                select(AccessProfile).where(AccessProfile.id == g.access_profile_id)
            )
            profile = prof_r.scalar_one_or_none()
            summaries.append(
                GrantSummary(
                    user_id=u.id,
                    grant_id=g.id,
                    scope=g.scope,
                    scope_name=name,
                    access_profile_name=profile.name if profile else "",
                )
            )
        first_user = authenticated_user_grants[0][0]
        log.info("auth.portal.mgmt.login.grant_selection", grant_count=len(summaries))
        return UnifiedLoginResponse(
            user_id=first_user.id,
            user_name=first_user.name,
            available_grants=summaries,
        )

    # ── User(s) matched credentials but none have portal-capable grants ──
    if any_user_creds_valid:
        # Log against the first matched user for audit trail
        failed_user = all_users[0]
        await log_action(
            db=db,
            action=MGMT_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(failed_user.id),
            actor_type=ActorType.USER,
            actor_id=failed_user.id,
            actor_email=failed_user.email,
            actor_name=failed_user.name,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal-capable access grants for this account",
        )

    # ── Neither table matched — consistent 401, never reveal which was checked ──
    if superadmin is not None:
        await log_action(
            db=db,
            action=AUTH_LOGIN_FAILED,
            entity_type="superadmin",
            entity_id=str(superadmin.id),
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
        )
    else:
        entity_id = str(all_users[0].id) if all_users else payload.email
        await log_action(
            db=db,
            action=MGMT_LOGIN_FAILED,
            entity_type="user",
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


async def issue_identity_token(
    db: AsyncSession, payload: IdentityTokenRequest
) -> UnifiedLoginResponse:
    """
    Issue tokens for the chosen identity after cross-identity disambiguation.

    Re-verifies credentials for the selected identity_type before issuing
    anything, to prevent identity enumeration by a caller probing types.

    Args:
        db: Active database session.
        payload: email, password, and the chosen identity_type
            ("superadmin" or "user").

    Returns:
        UnifiedLoginResponse: Portal tokens (superadmin), or management
        tokens / a grant list (user), depending on identity_type.

    Raises:
        HTTPException: 401 for invalid credentials or an unrecognised
            identity_type; 403 if the user has no portal-capable grants.
    """
    if payload.identity_type == "superadmin":
        superadmin = await _load_superadmin(db, payload.email)
        if (
            superadmin is None
            or not verify_password(payload.password, superadmin.password_hash)
            or not superadmin.is_active
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await _issue_superadmin_tokens(db, superadmin)

    if payload.identity_type == "user":
        # Same multi-user logic as login() — same email may belong to multiple Users
        all_users = await _load_users(db, payload.email)
        authenticated_user_grants: list[tuple[User, list[UserAccessGrant]]] = []
        any_creds_valid = False
        for candidate in all_users:
            if not candidate.is_active or not verify_password(payload.password, candidate.password_hash):
                continue
            any_creds_valid = True
            grants = await _portal_capable_grants(db, candidate.id)
            if grants:
                authenticated_user_grants.append((candidate, grants))

        if not any_creds_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not authenticated_user_grants:
            failed_user = all_users[0]
            await log_action(
                db=db,
                action=MGMT_LOGIN_FAILED,
                entity_type="user",
                entity_id=str(failed_user.id),
                actor_type=ActorType.USER,
                actor_id=failed_user.id,
                actor_email=failed_user.email,
                actor_name=failed_user.name,
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No portal-capable access grants for this account",
            )
        # Single user → use existing _resolve_user_login path
        if len(authenticated_user_grants) == 1:
            return await _resolve_user_login(db, authenticated_user_grants[0][0])
        # Multiple users → show combined picker
        flat: list[tuple[User, UserAccessGrant]] = [
            (u, g) for u, grants in authenticated_user_grants for g in grants
        ]
        summaries: list[GrantSummary] = []
        for u, g in flat:
            name = await _scope_name(db, g)
            prof_r = await db.execute(
                select(AccessProfile).where(AccessProfile.id == g.access_profile_id)
            )
            profile = prof_r.scalar_one_or_none()
            summaries.append(
                GrantSummary(
                    user_id=u.id,
                    grant_id=g.id,
                    scope=g.scope,
                    scope_name=name,
                    access_profile_name=profile.name if profile else "",
                )
            )
        first_user = authenticated_user_grants[0][0]
        return UnifiedLoginResponse(user_id=first_user.id, user_name=first_user.name, available_grants=summaries)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid identity_type",
        headers={"WWW-Authenticate": "Bearer"},
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
    result = await db.execute(select(User).where(User.id == payload.user_id))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash) or not user.is_active:
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

    # Portal access is gated on backend_role, not can_access_portal
    if not grant.backend_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This grant does not have backend access configured",
        )

    access, refresh = await _build_mgmt_token(db, user, grant)

    await log_action(
        db=db,
        action=MGMT_TOKEN_ISSUED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()

    log.info(
        "auth.portal.mgmt.token.issued",
        user_id=str(user.id),
        grant_id=str(grant.id),
        scope=grant.scope,
    )
    return UnifiedLoginResponse(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        user_name=user.name,
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
    result = await db.execute(select(User).where(User.id == user_id_str))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject a management refresh token minted before a token_version bump
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Re-issue as a single-grant token or return grant list if needed.
    # Since a refresh carries no grant_id, we check if the user still has
    # exactly one portal-capable grant; if multiple, they must re-select.
    grant_rows = await _portal_capable_grants(db, user.id)
    if not grant_rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No portal-capable access grants remain for this account",
        )

    if len(grant_rows) == 1:
        grant = grant_rows[0]
        new_access, new_refresh = await _build_mgmt_token(db, user, grant)
        await log_action(
            db=db,
            action=AUTH_TOKEN_REFRESHED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.token.refreshed", user_id=str(user.id))
        return UnifiedLoginResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user_id=user.id,
            user_name=user.name,
        )

    # Multiple grants — honour the default grant if set
    default_grants = [g for g in grant_rows if g.is_default]
    if default_grants:
        grant = default_grants[0]
        new_access, new_refresh = await _build_mgmt_token(db, user, grant)
        await log_action(
            db=db,
            action=AUTH_TOKEN_REFRESHED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
        )
        await db.commit()
        log.info("auth.portal.mgmt.token.refreshed.default_grant", user_id=str(user.id))
        return UnifiedLoginResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user_id=user.id,
            user_name=user.name,
        )

    # No default — caller must re-select via management-token
    summaries: list[GrantSummary] = []
    for grant in grant_rows:
        name = await _scope_name(db, grant)
        prof_r = await db.execute(
            select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
        )
        profile = prof_r.scalar_one_or_none()
        summaries.append(
            GrantSummary(
                grant_id=grant.id,
                scope=grant.scope,
                scope_name=name,
                access_profile_name=profile.name if profile else "",
            )
        )
    return UnifiedLoginResponse(
        user_id=user.id,
        user_name=user.name,
        available_grants=summaries,
    )
