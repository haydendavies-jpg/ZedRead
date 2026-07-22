"""Business logic for POS terminal authentication: login, logout, PIN set, and PIN verify."""

import os
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    DEVICE_REGISTERED,
    DEVICE_REPAIRED,
    DEVICE_TOKEN_RECOVERED,
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
from app.services import pos_device_service
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


async def _get_device_by_hardware_id(db: AsyncSession, hardware_id: str) -> PosDevice | None:
    """
    Fetch an active PosDevice by its stable hardware-anchored identifier.

    Used as a fallback when the terminal presents no device_token (e.g. the
    app was reinstalled and its local storage — and the token with it — was
    wiped), so the same physical device is still recognised rather than
    treated as brand-new.

    Args:
        db: Active database session.
        hardware_id: The OS-level identifier (e.g. Android ID) presented by the terminal.

    Returns:
        PosDevice | None: The matching device, or None if unknown/deregistered.
    """
    result = await db.execute(
        select(PosDevice).where(
            PosDevice.hardware_id == hardware_id,
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


async def _resolve_or_claim_device(
    db: AsyncSession,
    *,
    user: User,
    site_id: uuid.UUID,
    license_row: License,
    device_name: str,
    device_token: str | None,
    hardware_id: str | None = None,
) -> PosDevice | None:
    """
    Resolve this terminal's PosDevice for the target site, self-service.

    Resolution order: the presented device_token, if any; otherwise —
    since device_token lives in the app's own storage and is wiped by a
    reinstall — a fallback lookup by hardware_id (a stable OS-level
    identifier, e.g. Android ID, that survives reinstalls) to recognise a
    returning physical device that lost its token. Whichever way it's
    found, an existing device on site_id is reused as-is (no seat change,
    or a DEVICE_TOKEN_RECOVERED audit row if it was found only via
    hardware_id); found on a different site, it's re-paired here,
    consuming a seat on site_id's license (DEVICE_REPAIRED, or
    DEVICE_TOKEN_RECOVERED if the hardware_id fallback is what found it);
    genuinely unknown, a new device is claimed with a server-generated
    token, consuming a seat (DEVICE_REGISTERED). Every outcome but the
    plain same-site token match requires a free seat on license_row.

    Args:
        db: Active database session.
        user: The authenticated POS user, for audit attribution.
        site_id: The site being logged into.
        license_row: The target site's active License.
        device_name: Human-readable name to give a newly claimed device.
        device_token: The terminal's own previously-claimed token, if any.
        hardware_id: The terminal's stable hardware identifier, if any.

    Returns:
        PosDevice | None: The resolved device, or None if site_id's license
        has no free seat for a new claim/re-pair.
    """
    existing = await _get_device_by_token(db, device_token) if device_token else None
    recovered_via_hardware_id = False
    if existing is None and hardware_id:
        existing = await _get_device_by_hardware_id(db, hardware_id)
        recovered_via_hardware_id = existing is not None

    # Learn (or refresh) the hardware anchor whenever the terminal reports one,
    # so a future token loss can still be recovered.
    if existing is not None and hardware_id and existing.hardware_id != hardware_id:
        existing.hardware_id = hardware_id

    if existing is not None and existing.site_id == site_id:
        if recovered_via_hardware_id:
            await log_action(
                db=db,
                action=DEVICE_TOKEN_RECOVERED,
                entity_type="pos_device",
                entity_id=str(existing.id),
                actor_type=ActorType.USER,
                actor_id=user.id,
                actor_email=user.email,
                actor_name=user.name,
                after_state={"site_id": str(site_id)},
            )
        return existing

    active_count = await pos_device_service.count_active_devices_for_license(db, license_row.id)
    if active_count >= license_row.max_devices:
        return None

    if existing is not None:
        previous_site_id = existing.site_id
        existing.site_id = site_id
        existing.license_id = license_row.id
        await log_action(
            db=db,
            action=DEVICE_TOKEN_RECOVERED if recovered_via_hardware_id else DEVICE_REPAIRED,
            entity_type="pos_device",
            entity_id=str(existing.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            before_state={"site_id": str(previous_site_id)},
            after_state={"site_id": str(site_id)},
        )
        return existing

    device = PosDevice(
        id=uuid.uuid4(),
        site_id=site_id,
        license_id=license_row.id,
        device_name=device_name,
        device_token=str(uuid.uuid4()),
        hardware_id=hardware_id,
        is_active=True,
    )
    db.add(device)
    await db.flush()  # assign device.id before it's used as an audit entity_id
    await log_action(
        db=db,
        action=DEVICE_REGISTERED,
        entity_type="pos_device",
        entity_id=str(device.id),
        actor_type=ActorType.USER,
        actor_id=user.id,
        actor_email=user.email,
        actor_name=user.name,
        after_state={
            "site_id": str(site_id),
            "license_id": str(license_row.id),
            "device_name": device_name,
        },
    )
    return device


async def _finalize_login(
    db: AsyncSession,
    *,
    user: User,
    site_id: uuid.UUID,
    device_name: str,
    device_token: str | None,
    hardware_id: str | None = None,
) -> POSLoginResponse:
    """
    Resolve a chosen site into an issued POS access token.

    Verifies the user holds an active grant for site_id and that its
    License is active, self-service claims or re-pairs this terminal's
    device against that license's remaining seats, creates a session row,
    and issues the token.

    Args:
        db: Active database session.
        user: The already-credential-verified user.
        site_id: The site being logged into.
        device_name: Human-readable name to give a newly claimed device.
        device_token: The terminal's own previously-claimed token, if any.
        hardware_id: The terminal's stable hardware identifier, if any.

    Returns:
        POSLoginResponse: Access token and terminal context.

    Raises:
        HTTPException: 401 unknown site; 403 no active grant, inactive
            license, or no available seat for that site.
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

    device = await _resolve_or_claim_device(
        db,
        user=user,
        site_id=site_id,
        license_row=license_row,
        device_name=device_name,
        device_token=device_token,
        hardware_id=hardware_id,
    )
    if device is None:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"site_id": str(site_id), "reason": "no_available_seats"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No available license seats for this site",
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
        device_token=device.device_token,
    )


async def login(db: AsyncSession, payload: POSLoginRequest) -> POSLoginResponse:
    """
    Authenticate a POS user with email+password against this terminal.

    Self-service, no device pre-registration: the site is resolved purely
    from the user's own active grants — exactly one auto-resolves, zero is a
    403, two or more returns available_sites for the caller to choose via
    select_site(). is_pos_multi_site_enabled plays no role here — a picker
    is offered whenever there's genuinely more than one site to pick from,
    regardless of that flag's setting.

    Args:
        db: Active database session.
        payload: Login credentials, this device's name, and its own
            previously-claimed device_token (None on first-ever login).

    Returns:
        POSLoginResponse: Either a full token (with the claimed/re-paired
        device_token to persist), or available_sites to choose from.

    Raises:
        HTTPException: 401 invalid credentials; 403 no active grant on any
            site, inactive license, or no available license seat.
    """
    log.info("pos_auth.login.attempt", email=payload.email)

    # Throttle repeated login attempts against a single account (review S3)
    check_rate_limit(
        f"pos_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    user = await _authenticate_or_401(db, payload.email, payload.password)

    site_grants = await _get_user_site_grants(db, user.id)
    if not site_grants:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.USER,
            actor_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            after_state={"reason": "no_active_grant"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for any site",
        )

    if len(site_grants) == 1:
        target_site = site_grants[0][1]
        return await _finalize_login(
            db,
            user=user,
            site_id=target_site.id,
            device_name=payload.device_name,
            device_token=payload.device_token,
            hardware_id=payload.hardware_id,
        )

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
        payload: Credentials, the chosen site_id, this device's name, and
            its own previously-claimed device_token (None on first login).

    Returns:
        POSLoginResponse: Access token and terminal context.

    Raises:
        HTTPException: 401 invalid credentials; 403 no active grant,
            inactive license, or no available license seat for the site.
    """
    log.info("pos_auth.login.select_site.attempt", email=payload.email, site_id=str(payload.site_id))

    check_rate_limit(
        f"pos_login:{payload.email.lower()}",
        max_attempts=_LOGIN_MAX_ATTEMPTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )

    user = await _authenticate_or_401(db, payload.email, payload.password)

    return await _finalize_login(
        db,
        user=user,
        site_id=payload.site_id,
        device_name=payload.device_name,
        device_token=payload.device_token,
        hardware_id=payload.hardware_id,
    )


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


async def _pin_candidates_by_email(
    db: AsyncSession, email: str, pin: str, site_id: uuid.UUID
) -> list[tuple[User, UserPIN, AccessProfile]]:
    """
    Resolve PIN-verify candidates when the caller supplies an email.

    email disambiguates directly when more than one row shares it (see
    _get_users_by_email) — first find every candidate whose own PIN
    matches, then narrow to the one that also holds an active grant for
    this exact site.

    Args:
        db: Active database session.
        email: The incoming user's email.
        pin: The plaintext PIN to verify.
        site_id: The site the terminal is operating at.

    Returns:
        list[tuple[User, UserPIN, AccessProfile]]: Zero, one, or more
            candidates that both match the PIN and hold an active grant at
            site_id — the caller treats anything but exactly one as a
            failure (none found, or an unresolved collision).
    """
    candidates = await _get_users_by_email(db, email)
    pin_matches: list[tuple[User, UserPIN]] = []
    for candidate in candidates:
        if not candidate.is_active:
            continue
        pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == candidate.id))
        candidate_pin = pin_result.scalar_one_or_none()
        if candidate_pin is not None and await verify_password_async(pin, candidate_pin.pin_hash):
            pin_matches.append((candidate, candidate_pin))

    site_matches: list[tuple[User, UserPIN, AccessProfile]] = []
    for candidate, candidate_pin in pin_matches:
        grant_and_profile = await _get_active_grant_with_profile(db, candidate.id, site_id)
        if grant_and_profile is not None:
            _grant, profile = grant_and_profile
            site_matches.append((candidate, candidate_pin, profile))
    return site_matches


async def _pin_candidates_by_site(
    db: AsyncSession, site_id: uuid.UUID, pin: str
) -> list[tuple[User, UserPIN, AccessProfile]]:
    """
    Resolve PIN-verify candidates by site alone, with no email supplied.

    Real POS terminals overwhelmingly support switching the active operator
    by PIN alone (staff don't re-type an email each time) — every active
    user holding a site-scoped grant on site_id is a candidate, and each is
    tried against the PIN in turn. If two staff at the same site happen to
    have chosen the same PIN, this surfaces as a collision (more than one
    match) and the caller fails closed rather than guessing — the same
    policy _pin_candidates_by_email() already applies to its own
    multi-identity collision case.

    Args:
        db: Active database session.
        site_id: The site the terminal is operating at.
        pin: The plaintext PIN to verify.

    Returns:
        list[tuple[User, UserPIN, AccessProfile]]: Every active,
            site-granted user whose PIN matches.
    """
    result = await db.execute(
        select(User, UserAccessGrant, AccessProfile)
        .join(UserAccessGrant, UserAccessGrant.user_id == User.id)
        .join(AccessProfile, AccessProfile.id == UserAccessGrant.access_profile_id)
        .where(
            UserAccessGrant.site_id == site_id,
            UserAccessGrant.scope == "site",
            UserAccessGrant.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )
    site_matches: list[tuple[User, UserPIN, AccessProfile]] = []
    for user, _grant, profile in result.all():
        pin_result = await db.execute(select(UserPIN).where(UserPIN.user_id == user.id))
        user_pin = pin_result.scalar_one_or_none()
        if user_pin is not None and await verify_password_async(pin, user_pin.pin_hash):
            site_matches.append((user, user_pin, profile))
    return site_matches


async def verify_pin(
    db: AsyncSession,
    payload: PINVerifyRequest,
) -> PINVerifyResponse:
    """
    Verify a POS user's PIN and issue a new access token for terminal switch-user.

    Used when a different staff member wants to take over an active terminal
    session without a full email+password login. The outgoing user's session
    remains in the DB (ended_at is not set — the terminal manages that via
    the logout route added in Stage 7.4). email is optional: supplying it
    disambiguates directly (_pin_candidates_by_email); omitting it checks
    the PIN against every active user granted at site_id instead
    (_pin_candidates_by_site) — the switch-operator flow only asks for a PIN.

    Writes an audit log row on both success and failure.

    Args:
        db: Active database session.
        payload: PIN and site_id of the incoming user, plus an optional email.

    Returns:
        PINVerifyResponse: Fresh access token, user info, and profile name.

    Raises:
        HTTPException: 401 if the PIN is wrong or the user/grant does not exist.
    """
    if payload.email:
        log.info("pos_auth.pin.verify.attempt", email=payload.email, site_id=str(payload.site_id))
        # Throttle PIN guessing against a single account — PINs are only 4–6 digits
        check_rate_limit(
            f"pos_pin:{payload.email.lower()}",
            max_attempts=_PIN_MAX_ATTEMPTS,
            window_seconds=_PIN_WINDOW_SECONDS,
        )
        site_matches = await _pin_candidates_by_email(db, payload.email, payload.pin, payload.site_id)
        failure_entity_id = payload.email
    else:
        log.info("pos_auth.pin.verify.attempt", site_id=str(payload.site_id))
        # No account to key the throttle on — bucket by site/terminal instead.
        check_rate_limit(
            f"pos_pin_site:{payload.site_id}",
            max_attempts=_PIN_MAX_ATTEMPTS,
            window_seconds=_PIN_WINDOW_SECONDS,
        )
        site_matches = await _pin_candidates_by_site(db, payload.site_id, payload.pin)
        failure_entity_id = str(payload.site_id)

    if not site_matches:
        await log_action(
            db=db,
            action=POS_LOGIN_FAILED,
            entity_type="user",
            entity_id=failure_entity_id,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_email=payload.email,
            actor_name=None,
            after_state={"site_id": str(payload.site_id), "reason": "invalid_pin"},
        )
        await db.commit()
        log.warning("pos_auth.pin.verify.failed", site_id=str(payload.site_id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if len(site_matches) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active access grant for this site",
        )

    user, pin_record, access_profile = site_matches[0]

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
        email=user.email,
        access_profile_name=access_profile.name,
        is_pin_reset_required=pin_record.is_pin_reset_required,
    )
