"""Routes for User management — list, create, edit, deactivate/reactivate, set PIN, list grants.

Folds in what used to be the separate SuperAdmin-only /portal-users routes:
SuperAdmin access is a role on User (superadmin_role), not a separate
identity/table, so admin-portal rows are managed through this same route
set — only granting/changing superadmin_role itself is restricted to an
Admin-role portal admin (require_super_admin), mirroring the old
Admin-only restriction on managing other SuperAdmins.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.audit_actions import (
    USER_BACKEND_ROLE_UPDATED,
    USER_CREATED,
    USER_DEACTIVATED,
    USER_PASSWORD_ADMIN_SET,
    USER_PIN_ADMIN_SET,
    USER_REACTIVATED,
    USER_SUPERADMIN_ROLE_UPDATED,
    USER_UPDATED,
)
from app.constants.statuses import SuperAdminRole
from app.database import get_db
from app.models.access_profile import AccessProfile
from app.models.brand import Brand
from app.models.group import Group
from app.models.site import Site
from app.models.user import User
from app.models.user_access_grant import UserAccessGrant
from app.models.user_pin import UserPIN
from app.schemas.user import (
    EmailCheckOut,
    EnrichedGrantOut,
    GroupAccessOut,
    GroupScopeEntry,
    SetPinRequest,
    SiteGrantSummary,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import user_service
from app.services.audit_service import log_action
from app.utils.dependencies import CatalogAccess, get_current_superadmin, resolve_catalog_access
from app.utils.security import hash_password, normalize_email

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

# Valid backend role values — all carry full permissions for now
_BACKEND_ROLES = {"admin", "users", "reporting"}
# Valid admin-portal role values — mirrors SuperAdminRole
_SUPERADMIN_ROLES = {role.value for role in SuperAdminRole}


def _require_admin_role(actor: User) -> None:
    """
    Raise 403 unless the actor is an Admin-role portal admin.

    Granting/changing superadmin_role is an admin-portal-only, Admin-only
    action — a Reseller Staff portal admin may manage tenant Users freely
    but may not create or promote other portal admins, mirroring the old
    require_super_admin restriction on the standalone SuperAdmin routes.

    Args:
        actor: The authenticated portal admin performing the action.

    Raises:
        HTTPException: 403 if the actor is not Admin-role.
    """
    if actor.superadmin_role != SuperAdminRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an Admin-role portal admin may grant or change the admin-portal role",
        )


async def _attach_sites(
    db: AsyncSession,
    users: list[User],
) -> list[UserOut]:
    """
    Fetch active site grants and portal access flag for a batch of users.

    Returns full SiteGrantSummary objects (including grant_id and is_default) so
    the portal UI can show the primary site and offer a "Set primary" action.

    Args:
        db: Active database session.
        users: List of User ORM objects to enrich.

    Returns:
        list[UserOut]: Enriched user response objects.
    """
    if not users:
        return []

    user_ids = [u.id for u in users]
    # Exclude None — group-scoped master users and admin-portal-only rows have brand_id=NULL
    brand_ids = list({u.brand_id for u in users if u.brand_id is not None})

    # Brand and group names — batch query so the portal table can show them
    brand_q = (
        select(Brand.id, Brand.name, Group.name)
        .join(Group, Brand.group_id == Group.id)
        .where(Brand.id.in_(brand_ids))
    )
    brand_result = await db.execute(brand_q)
    brand_info: dict[uuid.UUID, tuple[str, str]] = {
        row[0]: (row[1], row[2]) for row in brand_result
    }

    # Site grants — single joined query returning grant + site + profile info
    grants_q = (
        select(
            UserAccessGrant.user_id,
            UserAccessGrant.id,
            UserAccessGrant.site_id,
            UserAccessGrant.is_default,
            Site.name,
            AccessProfile.name,
            AccessProfile.can_access_portal,
        )
        .join(Site, UserAccessGrant.site_id == Site.id)
        .join(AccessProfile, UserAccessGrant.access_profile_id == AccessProfile.id)
        .where(
            UserAccessGrant.user_id.in_(user_ids),
            UserAccessGrant.scope == "site",
            UserAccessGrant.is_active.is_(True),
        )
        .order_by(UserAccessGrant.is_default.desc(), Site.name)
    )
    grants_result = await db.execute(grants_q)
    grants_by_user: dict[uuid.UUID, list[SiteGrantSummary]] = {}
    portal_capable: set[uuid.UUID] = set()
    for (user_id, grant_id, site_id, is_default, site_name, profile_name, cap) in grants_result:
        grants_by_user.setdefault(user_id, []).append(
            SiteGrantSummary(
                grant_id=grant_id,
                site_id=site_id,
                site_name=site_name,
                is_default=is_default,
                access_profile_name=profile_name,
                can_access_portal=cap,
            )
        )
        if cap:
            portal_capable.add(user_id)

    return [
        UserOut(
            id=u.id,
            ref=u.ref,
            brand_id=u.brand_id,
            brand_name=brand_info.get(u.brand_id, ("", ""))[0],
            group_name=brand_info.get(u.brand_id, ("", ""))[1],
            name=u.name,
            first_name=u.first_name,
            last_name=u.last_name,
            email=u.email,
            backend_role=u.backend_role,
            superadmin_role=u.superadmin_role,
            is_active=u.is_active,
            is_pos_multi_site_enabled=u.is_pos_multi_site_enabled,
            site_grants=grants_by_user.get(u.id, []),
            has_portal_access=u.id in portal_capable,
        )
        for u in users
    ]


@router.get("", response_model=list[UserOut])
async def list_users(
    brand_id: str | None = None,
    site_id: str | None = None,
    superadmin_role: str | None = None,
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """List Users, optionally filtered by brand/site/admin-portal role. Portal admin only. Omit filters to see everyone."""
    q = select(User)
    if brand_id:
        q = q.where(User.brand_id == brand_id)

    if site_id:
        # Subquery: only users with an active site-scope grant for this site
        q = q.where(
            User.id.in_(
                select(UserAccessGrant.user_id).where(
                    UserAccessGrant.site_id == site_id,
                    UserAccessGrant.is_active.is_(True),
                )
            )
        )

    if superadmin_role:
        q = q.where(User.superadmin_role == superadmin_role)

    q = q.offset(skip).limit(limit).order_by(User.name)
    result = await db.execute(q)
    users = list(result.scalars().all())
    return await _attach_sites(db, users)


@router.get("/email-check", response_model=EmailCheckOut)
async def check_email(
    email: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
) -> EmailCheckOut:
    """
    Report whether an email is already registered, for the create-user and
    create-superadmin forms.

    Lets the portal skip the password field when the email already belongs to
    another row — the new row then shares that identity's sign-in password
    (ROLE_MODEL.md §3). Requires portal JWT.

    Args:
        email: The email being typed into the create-user or
            create-superadmin form.

    Returns:
        EmailCheckOut: Existence flag plus the matching row's name and
        whether it has a usable password.
    """
    owner = await user_service.find_email_owner(db, email)
    if owner is None:
        return EmailCheckOut(exists=False)
    return EmailCheckOut(
        exists=True,
        display_name=owner.name,
        has_password=owner.password_hash is not None,
    )


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """
    Fetch a single User by ID. Requires portal JWT.

    Used by the portal to resolve "who am I" after a portal login (the JWT's
    `sub` claim) as well as to fetch any other row for the admin-portal Users page.

    Args:
        user_id: UUID of the User.

    Returns:
        UserOut: The requested user, enriched with site grants.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    result_list = await _attach_sites(db, [user])
    return result_list[0]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """
    Create a new User. Requires portal JWT.

    Email handling: a brand-new email requires a password. An email that
    already belongs to another row does NOT create a competing password —
    the new row is linked to the existing sign-in password, so the person
    picks which platform to open at login. Supplying a fresh password for
    an already-registered email is rejected, to avoid two different
    passwords for the same login email.

    Setting superadmin_role additionally requires the caller to be
    Admin-role (see _require_admin_role).
    """
    if body.superadmin_role is not None:
        _require_admin_role(actor)

    # Emails are case-insensitive for login — normalize before storing/comparing.
    email = normalize_email(body.email) if body.email is not None else None

    # Resolve the sign-in password for the new row from the email's current state.
    password_hash: str | None = None
    if email is not None:
        existing_source = await user_service.find_email_owner(db, email)
        if existing_source is not None and existing_source.password_hash is not None:
            # Linked identity — reuse the existing password; reject a new one so
            # the shared email never ends up with two different passwords.
            if body.password is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email already has an account — leave the password blank; the new user shares the existing sign-in password.",
                )
            password_hash = existing_source.password_hash
        else:
            # Brand-new email (or an existing one whose owner has no password
            # yet) — a password is required to make this login usable.
            if body.password is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A password is required for a new email.",
                )
            password_hash = hash_password(body.password)

    group_id: uuid.UUID | None = None
    if body.brand_id is not None:
        brand_r = await db.execute(select(Brand).where(Brand.id == body.brand_id))
        brand = brand_r.scalar_one_or_none()
        if not brand:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
        group_id = brand.group_id

    user = User(
        group_id=group_id,
        brand_id=body.brand_id,
        first_name=body.first_name,
        last_name=body.last_name,
        name=f"{body.first_name} {body.last_name}",
        email=email,
        password_hash=password_hash,
        superadmin_role=body.superadmin_role,
    )
    db.add(user)
    await db.flush()

    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_CREATED,
        entity_type="user",
        entity_id=str(user.id),
        after_state={
            "name": user.name,
            "email": user.email,
            "brand_id": str(user.brand_id) if user.brand_id else None,
            "superadmin_role": user.superadmin_role,
        },
    )

    await db.commit()
    await db.refresh(user)
    return UserOut(
        id=user.id,
        ref=user.ref,
        brand_id=user.brand_id,
        name=user.name,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        backend_role=user.backend_role,
        superadmin_role=user.superadmin_role,
        is_active=user.is_active,
        is_pos_multi_site_enabled=user.is_pos_multi_site_enabled,
        site_grants=[],
        has_portal_access=False,
    )


@router.get("/{user_id}/grants", response_model=list[EnrichedGrantOut])
async def list_user_grants(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """
    List all active access grants for a User, enriched with scope entity names.

    Returns site, brand, and group grants with human-readable names so the
    edit-user panel can display a rich grants table without extra lookups.

    Args:
        user_id: UUID of the User.

    Returns:
        list[EnrichedGrantOut]: All active grants enriched with entity names.
    """
    # Verify user exists
    user_r = await db.execute(select(User).where(User.id == user_id))
    if user_r.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    grants_r = await db.execute(
        select(UserAccessGrant)
        .where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.is_active.is_(True),
        )
        .order_by(UserAccessGrant.scope, UserAccessGrant.created_at)
    )
    grants = list(grants_r.scalars().all())

    if not grants:
        return []

    # Batch-load all site/brand/group/profile IDs referenced by the grants
    site_ids = {g.site_id for g in grants if g.site_id}
    brand_ids = {g.brand_id for g in grants if g.brand_id}
    group_ids = {g.group_id for g in grants if g.group_id}
    profile_ids = {g.access_profile_id for g in grants}

    # Fetch site → (name, brand_id) mapping
    site_info: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
    if site_ids:
        sr = await db.execute(select(Site.id, Site.name, Site.brand_id).where(Site.id.in_(site_ids)))
        for s_id, s_name, s_brand_id in sr:
            site_info[s_id] = (s_name, s_brand_id)
            brand_ids.add(s_brand_id)  # ensure we load the site's brand too

    # Fetch brand → (name, group_id) mapping
    brand_info: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
    if brand_ids:
        br = await db.execute(select(Brand.id, Brand.name, Brand.group_id).where(Brand.id.in_(brand_ids)))
        for b_id, b_name, b_group_id in br:
            brand_info[b_id] = (b_name, b_group_id)
            group_ids.add(b_group_id)

    # Fetch group → name mapping
    group_info: dict[uuid.UUID, str] = {}
    if group_ids:
        gr = await db.execute(select(Group.id, Group.name).where(Group.id.in_(group_ids)))
        for g_id, g_name in gr:
            group_info[g_id] = g_name

    # Fetch profile → (name, can_access_portal) mapping
    profile_info: dict[uuid.UUID, tuple[str, bool]] = {}
    if profile_ids:
        pr = await db.execute(
            select(AccessProfile.id, AccessProfile.name, AccessProfile.can_access_portal)
            .where(AccessProfile.id.in_(profile_ids))
        )
        for p_id, p_name, p_cap in pr:
            profile_info[p_id] = (p_name, p_cap)

    result: list[EnrichedGrantOut] = []
    for g in grants:
        # Resolve site, brand, group names from the grant's FK
        resolved_site_id = g.site_id
        resolved_site_name: str | None = None
        resolved_brand_id = g.brand_id
        resolved_brand_name: str | None = None
        resolved_group_id = g.group_id
        resolved_group_name: str | None = None

        if g.scope == "site" and g.site_id:
            s_name, s_brand_id = site_info.get(g.site_id, ("", None))  # type: ignore[assignment]
            resolved_site_name = s_name or None
            if s_brand_id:
                resolved_brand_id = s_brand_id
                b_name, b_group_id = brand_info.get(s_brand_id, ("", None))  # type: ignore[assignment]
                resolved_brand_name = b_name or None
                if b_group_id:
                    resolved_group_id = b_group_id
                    resolved_group_name = group_info.get(b_group_id)

        elif g.scope == "brand" and g.brand_id:
            b_name, b_group_id = brand_info.get(g.brand_id, ("", None))  # type: ignore[assignment]
            resolved_brand_name = b_name or None
            if b_group_id:
                resolved_group_id = b_group_id
                resolved_group_name = group_info.get(b_group_id)

        elif g.scope == "group" and g.group_id:
            resolved_group_name = group_info.get(g.group_id)

        p_name, p_cap = profile_info.get(g.access_profile_id, ("", False))

        result.append(
            EnrichedGrantOut(
                grant_id=g.id,
                scope=g.scope,
                site_id=resolved_site_id,
                site_name=resolved_site_name,
                brand_id=resolved_brand_id,
                brand_name=resolved_brand_name,
                group_id=resolved_group_id,
                group_name=resolved_group_name,
                access_profile_id=g.access_profile_id,
                access_profile_name=p_name,
                can_access_portal=p_cap,
                is_default=g.is_default,
                is_active=g.is_active,
            )
        )

    return result


@router.get("/{user_id}/group-access", response_model=GroupAccessOut)
async def get_user_group_access(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """
    Return all brands and sites in the user's group with their current grant state.

    Every tenant-scoped User belongs to exactly one group via User.group_id.
    Each entry shows the current POS access profile, or null if no access is
    granted yet — so the portal can render the full access matrix rather
    than just the rows that already have grants.

    Args:
        user_id: UUID of the User.

    Returns:
        GroupAccessOut: Group info plus one entry per brand and per site.
    """
    user_r = await db.execute(select(User).where(User.id == user_id))
    user = user_r.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.group_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This row has no tenant scope (admin-portal-only user)",
        )

    group_r = await db.execute(select(Group).where(Group.id == user.group_id))
    group = group_r.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    # Fetch all brands in the group
    brands_r = await db.execute(
        select(Brand).where(Brand.group_id == group.id, Brand.is_active.is_(True)).order_by(Brand.name)
    )
    brands = list(brands_r.scalars().all())
    brand_ids = [b.id for b in brands]

    # Fetch all active sites across those brands
    sites_r = await db.execute(
        select(Site).where(Site.brand_id.in_(brand_ids), Site.is_active.is_(True)).order_by(Site.name)
    )
    sites = list(sites_r.scalars().all())

    # Build site lookup: brand_id → [sites]
    sites_by_brand: dict[uuid.UUID, list[Site]] = {}
    for s in sites:
        sites_by_brand.setdefault(s.brand_id, []).append(s)

    # Fetch all active grants for this user (group, brand, and site scope)
    grants_r = await db.execute(
        select(UserAccessGrant).where(
            UserAccessGrant.user_id == user_id,
            UserAccessGrant.is_active.is_(True),
        )
    )
    grants = list(grants_r.scalars().all())

    # Build grant lookups
    group_grant: UserAccessGrant | None = next(
        (g for g in grants if g.scope == "group" and g.group_id == group.id), None
    )
    brand_grant: dict[uuid.UUID, UserAccessGrant] = {g.brand_id: g for g in grants if g.brand_id}
    site_grant: dict[uuid.UUID, UserAccessGrant] = {g.site_id: g for g in grants if g.site_id}

    # Batch-fetch profiles for all referenced grants
    profile_ids = {g.access_profile_id for g in grants}
    profile_info: dict[uuid.UUID, tuple[str, bool]] = {}
    if profile_ids:
        pr = await db.execute(
            select(AccessProfile.id, AccessProfile.name, AccessProfile.can_access_portal)
            .where(AccessProfile.id.in_(profile_ids))
        )
        for p_id, p_name, p_cap in pr:
            profile_info[p_id] = (p_name, p_cap)

    entries: list[GroupScopeEntry] = []

    # Group row always first — backend role for the whole group scope
    entries.append(GroupScopeEntry(
        scope="group",
        grant_id=group_grant.id if group_grant else None,
        backend_role=group_grant.backend_role if group_grant else None,
    ))

    for b in brands:
        bg = brand_grant.get(b.id)
        p_name, p_cap = profile_info.get(bg.access_profile_id, (None, False)) if bg else (None, False)
        entries.append(GroupScopeEntry(
            scope="brand",
            brand_id=b.id,
            brand_name=b.name,
            grant_id=bg.id if bg else None,
            access_profile_id=bg.access_profile_id if bg else None,
            access_profile_name=p_name,
            can_access_portal=p_cap,
            is_default=False,
            backend_role=bg.backend_role if bg else None,
        ))

        for s in sites_by_brand.get(b.id, []):
            sg = site_grant.get(s.id)
            sp_name, sp_cap = profile_info.get(sg.access_profile_id, (None, False)) if sg else (None, False)
            entries.append(GroupScopeEntry(
                scope="site",
                brand_id=b.id,
                brand_name=b.name,
                site_id=s.id,
                site_name=s.name,
                grant_id=sg.id if sg else None,
                access_profile_id=sg.access_profile_id if sg else None,
                access_profile_name=sp_name,
                can_access_portal=sp_cap,
                is_default=sg.is_default if sg else False,
                backend_role=sg.backend_role if sg else None,
            ))

    return GroupAccessOut(group_id=group.id, group_name=group.name, entries=entries)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """Edit a User's name, email, backend_role, superadmin_role, POS site assignment, and/or password. Requires portal JWT."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_master_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Master User cannot be edited — its identity is tied to its site",
        )

    before: dict = {"name": user.name, "email": user.email, "backend_role": user.backend_role}

    if body.first_name is not None:
        user.first_name = body.first_name
    if body.last_name is not None:
        user.last_name = body.last_name
    if body.first_name is not None or body.last_name is not None:
        user.name = f"{user.first_name} {user.last_name}"
    if body.email is not None:
        # Emails are case-insensitive for login — normalize before storing/comparing.
        new_email = normalize_email(body.email)
        # Check for email conflict with another user
        dup = await db.execute(
            select(User).where(func.lower(User.email) == new_email, User.id != user.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        user.email = new_email

    if body.password is not None:
        if user.email is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User must have an email before a password can be set",
            )
        user.password_hash = hash_password(body.password)
        # Never write the raw or hashed password into the audit log.
        await log_action(
            db=db,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_name=actor.name,
            action=USER_PASSWORD_ADMIN_SET,
            entity_type="user",
            entity_id=str(user.id),
            after_state={"set_by_admin": True},
        )

    # backend_role uses a special sentinel: the field is present in the model
    # but we only update when the key was explicitly provided in the request body
    if "backend_role" in body.model_fields_set:
        if body.backend_role is not None and body.backend_role not in _BACKEND_ROLES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"backend_role must be one of: {sorted(_BACKEND_ROLES)} or null",
            )
        if body.backend_role is not None and (user.email is None or user.password_hash is None):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User must have an email and password before being granted backend access",
            )
        if user.backend_role != body.backend_role:
            await log_action(
                db=db,
                actor_id=actor.id,
                actor_email=actor.email,
                actor_name=actor.name,
                action=USER_BACKEND_ROLE_UPDATED,
                entity_type="user",
                entity_id=str(user.id),
                before_state={"backend_role": user.backend_role},
                after_state={"backend_role": body.backend_role},
            )
        user.backend_role = body.backend_role

    # superadmin_role uses the same sentinel pattern — only Admin-role portal
    # admins may grant/change it (ROLE_MODEL.md §1: "only grantable from the
    # admin portal", and here specifically Admin-role, not Reseller Staff).
    if "superadmin_role" in body.model_fields_set:
        if body.superadmin_role is not None and body.superadmin_role not in _SUPERADMIN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"superadmin_role must be one of: {sorted(_SUPERADMIN_ROLES)} or null",
            )
        if user.superadmin_role != body.superadmin_role:
            _require_admin_role(actor)
            if body.superadmin_role is not None and (user.email is None or user.password_hash is None):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User must have an email and password before being granted admin-portal access",
                )
            await log_action(
                db=db,
                actor_id=actor.id,
                actor_email=actor.email,
                actor_name=actor.name,
                action=USER_SUPERADMIN_ROLE_UPDATED,
                entity_type="user",
                entity_id=str(user.id),
                before_state={"superadmin_role": user.superadmin_role},
                after_state={"superadmin_role": body.superadmin_role},
            )
        user.superadmin_role = body.superadmin_role

    # POS - Site Assignment — same "not supplied" sentinel as backend_role/superadmin_role
    if "is_pos_multi_site_enabled" in body.model_fields_set and body.is_pos_multi_site_enabled is not None:
        user.is_pos_multi_site_enabled = body.is_pos_multi_site_enabled

    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_UPDATED,
        entity_type="user",
        entity_id=str(user.id),
        before_state=before,
        after_state={
            "name": user.name,
            "email": user.email,
            "backend_role": user.backend_role,
            "is_pos_multi_site_enabled": user.is_pos_multi_site_enabled,
        },
    )

    await db.commit()
    await db.refresh(user)
    result_list = await _attach_sites(db, [user])
    return result_list[0]


@router.post("/{user_id}/set-pin", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def set_pin_for_user(
    user_id: str,
    body: SetPinRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """
    Admin endpoint: set or reset a POS user's PIN.

    Creates the UserPIN row if it doesn't exist; updates it otherwise.
    The PIN is stored as an argon2 hash — the raw PIN is never persisted.

    Args:
        user_id: UUID of the POS user to set the PIN for.
        body: Contains the raw PIN (4–6 digits).
    """
    user_r = await db.execute(select(User).where(User.id == user_id))
    user = user_r.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    pin_r = await db.execute(select(UserPIN).where(UserPIN.user_id == user_id))
    pin_row = pin_r.scalar_one_or_none()

    new_hash = hash_password(body.pin)

    if pin_row:
        pin_row.pin_hash = new_hash
        # Admin-set PIN does not force a reset — it replaces the PIN cleanly
        pin_row.is_pin_reset_required = False
    else:
        pin_row = UserPIN(
            user_id=user.id,
            pin_hash=new_hash,
            is_pin_reset_required=False,
        )
        db.add(pin_row)

    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_PIN_ADMIN_SET,
        entity_type="user",
        entity_id=str(user.id),
        after_state={"set_by_admin": True},
    )

    await db.commit()


@router.post("/{user_id}/send-password-reset", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def send_password_reset(
    user_id: uuid.UUID,
    access: CatalogAccess = Depends(resolve_catalog_access),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Trigger a password-reset email for a User.

    Reachable by a portal admin or a management caller within their scope
    (see user_service.request_user_password_reset()). The user clicks the
    emailed link to /reset-password, consumed by the same endpoint
    portal-admin resets use (POST /auth/portal/reset-password).

    Args:
        user_id: The target User.
        access: Resolved catalog access.
        db: Active database session.
    """
    if access.pos_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset requires a management or portal JWT",
        )
    await user_service.request_user_password_reset(
        db,
        user_id=user_id,
        management_access=access.mgmt_access,
        superadmin=access.portal_access,
    )


@router.patch("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """Deactivate a User. Requires portal JWT. Cannot deactivate your own row."""
    if user_id == str(actor.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_master_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Master User cannot be deactivated — its identity is tied to its site",
        )

    user.is_active = False
    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_DEACTIVATED,
        entity_type="user",
        entity_id=str(user.id),
        after_state={"is_active": False},
    )

    await db.commit()
    await db.refresh(user)
    result_list = await _attach_sites(db, [user])
    return result_list[0]


@router.post("/{user_id}/reactivate", response_model=UserOut)
async def reactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_superadmin),
):
    """Reactivate a previously deactivated User. Requires portal JWT."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already active")

    user.is_active = True
    await log_action(
        db=db,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_name=actor.name,
        action=USER_REACTIVATED,
        entity_type="user",
        entity_id=str(user.id),
        before_state={"is_active": False},
        after_state={"is_active": True},
    )

    await db.commit()
    await db.refresh(user)
    result_list = await _attach_sites(db, [user])
    return result_list[0]
