"""Business logic for unified portal login and management JWT issuance.

Extends the portal login flow to also accept POS user credentials. Portal
access for a User is gated on backend_role (per-grant), not on the POS
access profile. superadmin_role and grant-based backend access are two
independent capabilities a single `users` row may hold (ROLE_MODEL.md §1) —
a "hybrid" row can have both. If a row matches only one capability, the
matching token is issued directly. If a row (or several rows sharing an
email — users.email is non-unique) together offer more than one capability,
the caller is shown the available identities (ROLE_MODEL.md §3) and must
select one via POST /auth/portal/identity-token before any token is issued.
"""

import os
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
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
    normalize_email,
    verify_password_async,
)

log = structlog.get_logger(__name__)

# Login throttle: at most _LOGIN_MAX_ATTEMPTS per account per window
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))


async def _load_users_by_email(db: AsyncSession, email: str) -> list[User]:
    """Fetch all users with the given email, case-insensitively (multiple allowed — same person can manage several entities, or hold a separate portal-admin row)."""
    result = await db.execute(select(User).where(func.lower(User.email) == normalize_email(email)))
    return list(result.scalars().all())


async def _authenticate_candidates(
    db: AsyncSession, email: str, password: str
) -> tuple[list[User], list[User], list[tuple[User, list[UserAccessGrant]]], bool]:
    """
    Verify credentials against every `users` row matching the email and split by capability.

    A single row can offer both capabilities at once (a hybrid account) —
    both lists may include the same row.

    Args:
        db: Active session.
        email: The login email.
        password: The plaintext password to verify.

    Returns:
        tuple: (all matching rows, superadmin-capable rows, (user, grants)
        pairs for rows with at least one portal-capable grant, whether any
        row's credentials were valid at all).
    """
    candidates = await _load_users_by_email(db, email)
    superadmin_rows: list[User] = []
    user_grant_pairs: list[tuple[User, list[UserAccessGrant]]] = []
    any_creds_valid = False

    for candidate in candidates:
        if not candidate.is_active or not await verify_password_async(password, candidate.password_hash):
            continue
        any_creds_valid = True
        if candidate.superadmin_role is not None:
            superadmin_rows.append(candidate)
        grants = await _portal_capable_grants(db, candidate.id)
        if grants:
            user_grant_pairs.append((candidate, grants))

    return candidates, superadmin_rows, user_grant_pairs, any_creds_valid


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


async def _issue_superadmin_tokens(db: AsyncSession, superadmin: User) -> UnifiedLoginResponse:
    """
    Issue portal access + refresh tokens for an authenticated portal admin.

    Writes the AUTH_LOGIN_SUCCESS audit row and commits the transaction.

    Args:
        db: Active database session.
        superadmin: The authenticated User row (superadmin_role set).

    Returns:
        UnifiedLoginResponse: Portal token pair, no user_id/grant fields.
    """
    access_token = create_access_token(str(superadmin.id), superadmin.superadmin_role, superadmin.token_version)
    refresh_token = create_refresh_token(str(superadmin.id), superadmin.token_version)
    await log_action(
        db=db,
        action=AUTH_LOGIN_SUCCESS,
        entity_type="user",
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
    Unified portal login, disambiguating across a row's available capabilities.

    Loads every `users` row matching the email (there may be more than one —
    email is non-unique) and verifies credentials independently per row. If
    exactly one capability matches across all valid rows (a bare superadmin
    row, or a single portal-capable grant), the matching token is issued
    directly. If more than one capability matches — a hybrid row with both
    superadmin_role and grants, or several rows sharing an email — neither
    token is issued yet: the caller is shown the available identities
    (ROLE_MODEL.md §3) and must call POST /auth/portal/identity-token with
    the chosen identity_type. If no row matches → consistent 401 (no
    information about whether the email exists at all).

    Args:
        db: Active database session.
        payload: Login credentials (email + password).

    Returns:
        UnifiedLoginResponse: Tokens, a grant list, or an identity list,
        depending on what matches the supplied email.

    Raises:
        HTTPException: 401 for invalid credentials; 403 if a row matches
            but has no portal-capable grants or superadmin_role.
    """
    log.info("auth.portal.login.attempt", email=payload.email)

    # Throttle repeated attempts against a single account before doing any
    # credential work — mitigates password brute-forcing (review finding S3).
    check_rate_limit(
        f"portal_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    candidates, superadmin_rows, user_grant_pairs, any_creds_valid = await _authenticate_candidates(
        db, payload.email, payload.password
    )
    superadmin_valid = bool(superadmin_rows)
    user_valid = bool(user_grant_pairs)

    # ── Both capabilities valid → disambiguate, issue no tokens yet ──
    if superadmin_valid and user_valid:
        log.info("auth.portal.login.identity_selection", email=payload.email)
        first_user = user_grant_pairs[0][0]
        return UnifiedLoginResponse(
            available_identities=[
                IdentitySummary(identity_type="superadmin", display_name=superadmin_rows[0].name),
                IdentitySummary(identity_type="user", display_name=first_user.name),
            ]
        )

    # ── Only superadmin capability valid ────────────────────────────────
    if superadmin_valid:
        return await _issue_superadmin_tokens(db, superadmin_rows[0])

    # ── One or more rows valid with grants ──────────────────────────────
    if user_valid:
        # Flatten all (user, grant) pairs across all authenticated rows
        flat: list[tuple[User, UserAccessGrant]] = [
            (u, g) for u, grants in user_grant_pairs for g in grants
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

        # Multiple grants across one or more rows → show picker; caller selects via management-token
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
        first_user = user_grant_pairs[0][0]
        log.info("auth.portal.mgmt.login.grant_selection", grant_count=len(summaries))
        return UnifiedLoginResponse(
            user_id=first_user.id,
            user_name=first_user.name,
            available_grants=summaries,
        )

    # ── Row(s) matched credentials but none offer a capability ──
    if any_creds_valid:
        # Log against the first matched row for audit trail
        failed_user = next(c for c in candidates if c.is_active)
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

    # ── No row matched — consistent 401, never reveal whether the email exists ──
    # A candidate carrying superadmin_role (regardless of whether its password
    # check passed) logs as a portal-admin-flavoured failure; otherwise it's a
    # management-flavoured failure — mirrors the pre-merge two-table check.
    superadmin_candidate = next((c for c in candidates if c.superadmin_role is not None), None)
    if superadmin_candidate is not None:
        await log_action(
            db=db,
            action=AUTH_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(superadmin_candidate.id),
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
        )
    else:
        entity_id = str(candidates[0].id) if candidates else payload.email
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
    candidates, superadmin_rows, user_grant_pairs, any_creds_valid = await _authenticate_candidates(
        db, payload.email, payload.password
    )

    if payload.identity_type == "superadmin":
        if not superadmin_rows:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await _issue_superadmin_tokens(db, superadmin_rows[0])

    if payload.identity_type == "user":
        if not any_creds_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user_grant_pairs:
            failed_user = next(c for c in candidates if c.is_active)
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
        # Single row with grants → use existing _resolve_user_login path
        if len(user_grant_pairs) == 1:
            return await _resolve_user_login(db, user_grant_pairs[0][0])
        # Multiple rows with grants → show combined picker
        flat: list[tuple[User, UserAccessGrant]] = [
            (u, g) for u, grants in user_grant_pairs for g in grants
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
        first_user = user_grant_pairs[0][0]
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

    if user is None or not await verify_password_async(payload.password, user.password_hash) or not user.is_active:
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
