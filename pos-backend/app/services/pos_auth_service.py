"""Business logic for POS terminal authentication: login, logout, PIN set, and PIN verify."""

import os
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    DEVICE_REPAIRED,
    POS_LOGIN_FAILED,
    POS_LOGIN_SUCCESS,
    POS_LOGOUT,
    POS_PIN_SET,
    POS_PIN_VERIFIED,
)
from app.constants.statuses import ActorType
from app.models.access_profile import AccessProfile
from app.models.license import License
from app.models.pos_device import PosDevice
from app.models.user import User
from app.models.site import Site
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.models.user_pos_session import UserPOSSession
from app.schemas.pos_auth import (
    PINSetRequest,
    PINVerifyRequest,
    PINVerifyResponse,
    POSLoginRequest,
    POSLoginResponse,
    POSSiteTokenRequest,
    SiteOption,
)
from app.services.audit_service import log_action
from app.utils.rate_limit import check_rate_limit
from app.utils.security import (
    create_pos_access_token,
    hash_password,
    normalize_email,
    verify_password_async,
)

log = structlog.get_logger(__name__)

# Login/PIN throttle: at most N attempts per account per window. PINs are only
# 4–6 digits, so throttling per-account is the main brute-force defence (S3).
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
_PIN_MAX_ATTEMPTS = int(os.getenv("PIN_RATE_LIMIT", "10"))
_PIN_WINDOW_SECONDS = int(os.getenv("PIN_RATE_WINDOW_SECONDS", "300"))


async def _get_users_by_email(db: AsyncSession, email: str) -> list[User]:
    """
    Fetch every users row matching the email, case-insensitively.

    users.email is intentionally non-unique (migration 0031) — the same
    email can belong to more than one row (Master User on multiple brands,
    or a separate pure-SuperAdmin row created with the same email as a
    POS-capable row per migration 0050's hybrid-account design). A plain
    `.scalar_one_or_none()` lookup crashes with MultipleResultsFound the
    moment two rows share an email — mirrors
    management_auth_service._load_users_by_email's handling of the same
    non-uniqueness.

    Args:
        db: Active database session.
        email: The email address to look up.

    Returns:
        list[User]: Every matching row, usually zero or one.
    """
    result = await db.execute(select(User).where(func.lower(User.email) == normalize_email(email)))
    return list(result.scalars().all())


async def _has_active_grant(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """
    Check whether a user holds at least one active access grant anywhere.

    Args:
        db: Active database session.
        user_id: The user to check.

    Returns:
        bool: True if at least one active UserAccessGrant row exists.
    """
    result = await db.execute(
        select(UserAccessGrant.id)
        .where(UserAccessGrant.user_id == user_id, UserAccessGrant.is_active == True)  # noqa: E712
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _resolve_single_valid_user(db: AsyncSession, valid: list[User]) -> User | None:
    """
    Narrow a list of credential-valid users sharing an email down to one.

    The overwhelmingly common case is a single match, returned directly —
    this preserves every existing single-row behavior downstream (e.g. a
    grant-less match still proceeds to a 403 there, not a 401 here). Only
    when credentials validate for more than one row (a genuine email
    collision) does this break the tie in favor of a row holding at least
    one active access grant — a pure SuperAdmin-only row can never
    complete a POS login, so it loses to one that can.

    Args:
        db: Active database session.
        valid: Users whose credentials already validated.

    Returns:
        User | None: The single resolved user, or None if still zero or
        more than one after the grant-based tiebreak.
    """
    if len(valid) == 1:
        return valid[0]
    if len(valid) == 0:
        return None
    with_grants = [c for c in valid if await _has_active_grant(db, c.id)]
    return with_grants[0] if len(with_grants) == 1 else None


async def _get_active_grant_with_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    site_id: uuid.UUID,
) -> tuple[UserAccessGrant, AccessProfile] | None:
    """
    Fetch the active UserAccessGrant and its AccessProfile for a user+site pair.

    Args:
        db: Active database session.
        user_id: The POS user UUID.
        site_id: The site UUID.

    Returns:
        Tuple of (grant, profile) if an active grant exists, otherwise None.
    """
    grant_result = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.site_id == site_id,
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    grant = grant_result.scalar_one_or_none()
    if grant is None:
        return None

    profile_result = await db.execute(
        select(AccessProfile).where(AccessProfile.id == grant.access_profile_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        return None

    return grant, profile


async def _get_user_site_grants(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[UserAccessGrant, Site]]:
    """
    Fetch every active site-scoped grant for a user, joined to its site.

    Only scope='site' grants are considered — brand/group-scoped grants are
    not resolved down to individual sites for POS login, matching the
    existing single-site lookup in _get_active_grant_with_profile().

    Args:
        db: Active database session.
        user_id: The POS user UUID.

    Returns:
        list[tuple[UserAccessGrant, Site]]: One pair per active site grant.
    """
    result = await db.execute(
        select(UserAccessGrant, Site)
        .join(Site, Site.id == UserAccessGrant.site_id)
        .where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.scope == "site",
            UserAccessGrant.is_active == True,  # noqa: E712
        )
    )
    return list(result.all())


async def _get_device_by_token(db: AsyncSession, device_token: str) -> PosDevice | None:
    """
    Fetch an active PosDevice by its terminal token.

    Args:
        db: Active database session.
        device_token: The token presented by the terminal.

    Returns:
        PosDevice | None: The matching device, or None if unknown/deregistered.
    """
    result = await db.execute(
        select(PosDevice).where(
            PosDevice.device_token == device_token,
            PosDevice.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _get_active_license(db: AsyncSession, site_id: uuid.UUID) -> License | None:
    """
    Fetch the active License for a site, if any.

    Args:
        db: Active database session.
        site_id: The site UUID to check.

    Returns:
        License | None: The active license, or None if missing/expired/disabled.
    """
    result = await db.execute(
        select(License).where(License.site_id == site_id, License.status == "active")
    )
    return result.scalar_one_or_none()


async def _authenticate_or_401(db: AsyncSession, email: str, password: str) -> User:
    """
    Verify email+password against every row sharing that email and return
    the one matching user, raising 401 on any failure.

    Checks every candidate rather than short-circuiting on the first match,
    to avoid a timing attack that could reveal whether an email exists.

    Args:
        db: Active database session.
        email: Login email.
        password: Plaintext password to verify.

    Returns:
        User: The single authenticated, active user.

    Raises:
        HTTPException: 401 with a generic message if credentials are
            invalid, the user is inactive, or more than one candidate's
            credentials validate and the grant-based tiebreak in
            _resolve_single_valid_user still can't narrow it to one —
            failing closed rather than guessing which one to sign in as.
            Writes a POS_LOGIN_FAILED audit row first.
    """
    candidates = await _get_users_by_email(db, email)
    valid = [
        c for c in candidates
        if c.is_active and await verify_password_async(password, c.password_hash)
    ]
    user = await _resolve_single_valid_user(db, valid)
    if user is not None:
        return user

    entity_id = str(candidates[0].id) if len(candidates) == 1 else email
    reason = "ambiguous_credentials" if len(valid) > 1 else "invalid_credentials"
    await log_action(
        db=db,
        action=POS_LOGIN_FAILED,
        entity_type="user",
        entity_id=entity_id,
        actor_type=ActorType.USER,
        actor_id=None,
        actor_email=email,
        actor_name=None,
        after_state={"reason": reason},
    )
    await db.commit()
    log.warning("pos_auth.login.failed", email=email, reason=reason)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _finalize_login(
    db: AsyncSession, *, user: User, site_id: uuid.UUID, device: PosDevice
) -> POSLoginResponse:
    """
    Resolve a chosen site into an issued POS access token.

    Verifies the user holds an active grant for site_id and that its
    License is active, re-pairs the device to site_id if it differs from
    the device's current pairing (writing a DEVICE_REPAIRED audit row),
    creates a session row, and issues the token.

    Args:
        db: Active database session.
        user: The already-credential-verified user.
        site_id: The site being logged into.
        device: The calling terminal's PosDevice row.

    Returns:
        POSLoginResponse: Access token and terminal context.

    Raises:
        HTTPException: 401 unknown site; 403 no active grant or inactive
            license for that site.
    """
    site_result = await db.execute(select(Site).where(Site.id == site_id))
    site = site_result.scalar_one_or_none()
    if site is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(site_id), "reason": "site_not_found"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    grant_and_profile = await _get_active_grant_with_profile(db, user.id, site_id)
    if grant_and_profile is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(site_id), "reason": "no_active_grant"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )
    _grant, access_profile = grant_and_profile

    license_row = await _get_active_license(db, site_id)
    if license_row is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(site_id), "reason": "license_inactive"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This device's license is inactive",
        )

    # Re-pair the device only when the resolved site differs from its current
    # pairing — a Master/roaming user overriding it for this session, per the
    # locked-in "device stays pinned unless explicitly re-paired" decision.
    if device.site_id != site_id:
        previous_site_id = device.site_id
        device.site_id = site_id
        await log_action(
            db=db,
            action=DEVICE_REPAIRED,
            entity_type="pos_device",
            entity_id=str(device.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            before_state={"site_id": str(previous_site_id)},
            after_state={"site_id": str(site_id)},
        )

    pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
    pin_record = pin_result.scalar_one_or_none()
    is_pin_reset_required = pin_record.is_pin_reset_required if pin_record else True

    jti = str(uuid.uuid4())
    session = UserPOSSession(
        id=uuid.uuid4(), user_id=user.id, site_id=site_id, device_id=device.id, token_jti=jti
    )
    db.add(session)

    access_token = create_pos_access_token(str(user.id), str(site_id), jti, str(device.id))

    await log_action(
        db=db,
        action=POS_LOGIN_SUCCESS,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "site_id": str(site_id),
            "access_profile": access_profile.name,
            "session_jti": jti,
        },
    )
    await db.commit()

    log.info("pos_auth.login.success", user_id=str(user.id), site_id=str(site_id))
    return POSLoginResponse(
        access_token=access_token,
        user_id=user.id,
        user_name=user.name,
        site_id=site_id,
        site_name=site.name,
        access_profile_name=access_profile.name,
        is_pin_reset_required=is_pin_reset_required,
    )


async def login(db: AsyncSession, payload: POSLoginRequest) -> POSLoginResponse:
    """
    Authenticate a POS user with email+password against this terminal.

    The caller never supplies a site_id — the site is resolved from the
    device's own pairing (device_token) and the user's active grants. When
    the user's is_pos_multi_site_enabled flag is set and they hold grants on
    more than one site, returns available_sites instead of a token; the
    caller finalizes the choice via select_site().

    Args:
        db: Active database session.
        payload: Login credentials and the terminal's device_token.

    Returns:
        POSLoginResponse: Either a full token, or available_sites to choose from.

    Raises:
        HTTPException: 401 invalid credentials/unknown site; 404 unknown or
            deregistered device; 403 no active grant or inactive license.
    """
    log.info("pos_auth.login.attempt", email=payload.email)

    # Throttle repeated login attempts against a single account (review S3)
    check_rate_limit(
        f"pos_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    user = await _authenticate_or_401(db, payload.email, payload.password)

    device = await _get_device_by_token(db, payload.device_token)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not registered"
        )

    if not user.is_pos_multi_site_enabled:
        return await _finalize_login(db, user=user, site_id=device.site_id, device=device)

    site_grants = await _get_user_site_grants(db, user.id)
    if len(site_grants) <= 1:
        # Nothing to choose between — resolve to the device's paired site if
        # the user has a grant there, else their one granted site (if any).
        paired_site_granted = any(site.id == device.site_id for _grant, site in site_grants)
        if paired_site_granted or not site_grants:
            target_site_id = device.site_id
        else:
            target_site_id = site_grants[0][1].id
        return await _finalize_login(db, user=user, site_id=target_site_id, device=device)

    log.info("pos_auth.login.site_selection", user_id=str(user.id), site_count=len(site_grants))
    return POSLoginResponse(
        user_id=user.id,
        user_name=user.name,
        available_sites=[
            SiteOption(site_id=site.id, site_name=site.name) for _grant, site in site_grants
        ],
    )


async def select_site(db: AsyncSession, payload: POSSiteTokenRequest) -> POSLoginResponse:
    """
    Finalize a multi-site POS login by choosing one of the offered sites.

    Re-verifies credentials rather than trusting a bare site_id, since no
    intermediate token is issued between login() and this call — mirrors the
    portal's management-token re-verification pattern.

    Args:
        db: Active database session.
        payload: Credentials, device_token, and the chosen site_id.

    Returns:
        POSLoginResponse: Access token and terminal context.

    Raises:
        HTTPException: 401 invalid credentials; 404 unknown device; 403 no
            active grant or inactive license for the chosen site.
    """
    log.info("pos_auth.login.select_site.attempt", email=payload.email, site_id=str(payload.site_id))

    check_rate_limit(
        f"pos_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    user = await _authenticate_or_401(db, payload.email, payload.password)

    device = await _get_device_by_token(db, payload.device_token)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Device not registered"
        )

    return await _finalize_login(db, user=user, site_id=payload.site_id, device=device)


async def logout(db: AsyncSession, user: User, jti: str) -> None:
    """
    End the POS session identified by the token's jti, revoking that token.

    Sets ``ended_at`` on the matching ``user_pos_sessions`` row so
    resolve_access() rejects the token on its next use. Idempotent: if the
    session is already ended (or unknown), the call still succeeds so a
    double-logout from the terminal is not an error.

    Args:
        db: Active database session.
        user: The authenticated POS user (from resolve_access).
        jti: The ``jti`` claim of the token being logged out.

    Returns:
        None
    """
    log.info("pos_auth.logout", user_id=str(user.id))

    # Find the still-active session for this token
    session_result = await db.execute(
        select(UserPOSSession).where(
            UserPOSSession.token_jti == jti,
            UserPOSSession.ended_at.is_(None),  # only an active session can be ended
        )
    )
    session = session_result.scalar_one_or_none()

    if session is not None:
        # Mark the session ended — this is what revokes the token going forward
        session.ended_at = datetime.now(UTC)

    await log_action(
        db=db,
        action=POS_LOGOUT,
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={"session_jti": jti},
    )
    await db.commit()
    log.info("pos_auth.logout.complete", user_id=str(user.id))


async def set_pin(
    db: AsyncSession,
    user: User,
    payload: PINSetRequest,
) -> None:
    """
    Set or replace the PIN for the authenticated POS user.

    Upserts the user_pins row — creates on first call, updates on subsequent
    calls. Clears is_pin_reset_required on success so the terminal stops
    prompting for a new PIN.

    Args:
        db: Active database session.
        user: The authenticated POS user (from resolve_access dependency).
        payload: The new PIN (4–6 digits, validated by Pydantic).

    Returns:
        None
    """
    log.info("pos_auth.pin.set", user_id=str(user.id))

    pin_hash = hash_password(payload.pin)

    # Upsert: update existing row or create new one
    existing_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
    existing = existing_result.scalar_one_or_none()

    if existing is not None:
        existing.pin_hash = pin_hash
        existing.is_pin_reset_required = False
    else:
        pin_record = UserPIN(
            id=uuid.uuid4(),
            user_id=user.id,
            pin_hash=pin_hash,
            is_pin_reset_required=False,
        )
        db.add(pin_record)

    await log_action(
        db=db,
        action=POS_PIN_SET,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
    )
    await db.commit()
    log.info("pos_auth.pin.set.complete", user_id=str(user.id))


async def verify_pin(
    db: AsyncSession,
    payload: PINVerifyRequest,
) -> PINVerifyResponse:
    """
    Verify a POS user's PIN and issue a new access token for terminal switch-user.

    Used when a different staff member wants to take over an active terminal
    session without a full email+password login. The outgoing user's session
    remains in the DB (ended_at is not set — the terminal manages that via
    the logout route added in Stage 7.4).

    Writes an audit log row on both success and failure.

    Args:
        db: Active database session.
        payload: Email, PIN, and site_id of the incoming user.

    Returns:
        PINVerifyResponse: Fresh access token, user info, and profile name.

    Raises:
        HTTPException: 401 if the PIN is wrong or the user/grant does not exist.
    """
    log.info("pos_auth.pin.verify.attempt", email=payload.email, site_id=str(payload.site_id))

    # Throttle PIN guessing against a single account — PINs are only 4–6 digits
    check_rate_limit(
        f"pos_pin:{payload.email.lower()}",
        max_attempts=_PIN_MAX_ATTEMPTS,
        window_seconds=_PIN_WINDOW_SECONDS,
    )

    # payload.site_id disambiguates directly when more than one row shares
    # this email (see _get_users_by_email) — first find every candidate
    # whose own PIN matches, then narrow to the one that also holds an
    # active grant for this exact site, instead of resolving "the" user by
    # email alone.
    candidates = await _get_users_by_email(db, payload.email)
    pin_matches: list[tuple[User, UserPIN]] = []
    for candidate in candidates:
        if not candidate.is_active:
            continue
        pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == candidate.id))
        candidate_pin = pin_result.scalar_one_or_none()
        if candidate_pin is not None and await verify_password_async(payload.pin, candidate_pin.pin_hash):
            pin_matches.append((candidate, candidate_pin))

    if not pin_matches:
        entity_id = str(candidates[0].id) if len(candidates) == 1 else payload.email
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
            after_state={"site_id": str(payload.site_id), "reason": "invalid_pin"},
        )
        await db.commit()
        log.warning("pos_auth.pin.verify.failed", email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Narrow the PIN-valid candidates to the one that can access this site.
    # Zero means none of them can; more than one means the same PIN was
    # independently set on multiple accounts that can both access it — an
    # unresolved multi-identity collision, so this fails rather than guesses.
    site_matches = []
    for candidate, candidate_pin in pin_matches:
        candidate_grant = await _get_active_grant_with_profile(db, candidate.id, payload.site_id)
        if candidate_grant is not None:
            site_matches.append((candidate, candidate_pin, candidate_grant))

    if len(site_matches) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

    user, pin_record, grant_and_profile = site_matches[0]

    _grant, access_profile = grant_and_profile

    # Carry device context forward when the caller supplies it, so a
    # switched-in user's session still gates on the terminal's register
    # session — see PINVerifyRequest.device_token docstring
    device = await _get_device_by_token(db, payload.device_token) if payload.device_token else None

    # Create a new session row for the incoming user's switch-user token
    jti = str(uuid.uuid4())
    session = UserPOSSession(
        id=uuid.uuid4(),
        user_id=user.id,
        site_id=payload.site_id,
        device_id=device.id if device else None,
        token_jti=jti,
    )
    db.add(session)

    access_token = create_pos_access_token(
        str(user.id), str(payload.site_id), jti, str(device.id) if device else None
    )

    await log_action(
        db=db,
        action=POS_PIN_VERIFIED,
        entity_type="user",
        entity_id=str(user.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "site_id": str(payload.site_id),
            "access_profile": access_profile.name,
            "session_jti": jti,
        },
    )
    await db.commit()

    log.info("pos_auth.pin.verify.success", user_id=str(user.id), site_id=str(payload.site_id))
    return PINVerifyResponse(
        access_token=access_token,
        user_id=user.id,
        user_name=user.name,
        access_profile_name=access_profile.name,
        is_pin_reset_required=pin_record.is_pin_reset_required,
    )
