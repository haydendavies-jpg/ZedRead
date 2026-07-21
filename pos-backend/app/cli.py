"""Management CLI for ZedRead POS.

Run with: python -m app.cli <command>

Commands:
  bootstrap-super-admin   Create the initial Admin-role portal admin (a User
                          with superadmin_role='admin', no tenant scope).
                          Refuses to run if an Admin-role portal admin already exists.
  wipe-hierarchy          Permanently delete every Group, Brand, and Site, plus
                          everything that depends on them. Irreversible.
"""

import asyncio
import getpass

import structlog
import typer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.constants.audit_actions import HIERARCHY_WIPED, USER_CREATED
from app.constants.statuses import ActorType, SuperAdminRole
from app.logging_config import configure_logging
from app.models.brand import Brand
from app.models.group import Group
from app.models.site import Site
from app.models.user import User
from app.services.access_profile_service import seed_system_profiles
from app.services.audit_service import log_action
from app.utils.security import hash_password

configure_logging()
log = structlog.get_logger(__name__)

cli = typer.Typer(help="ZedRead POS management commands.")


def _get_database_url() -> str:
    """
    Read DATABASE_URL from environment with a safe local-dev fallback.

    Returns:
        str: The async PostgreSQL connection URL.
    """
    import os

    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://zedread:zedread@localhost:5432/zedread",
    )


async def _bootstrap_super_admin_async(non_interactive: bool = False) -> None:
    """
    Core async logic for the bootstrap-super-admin command.

    Creates the first Admin-role portal admin (a User row with
    superadmin_role='admin', no group/brand scope).
    Exits with an error if an Admin-role portal admin already exists to prevent duplicates.

    Args:
        non_interactive: When True, reads BOOTSTRAP_EMAIL, BOOTSTRAP_NAME,
                         BOOTSTRAP_PASSWORD from environment instead of prompting.
    """
    import os

    engine = create_async_engine(_get_database_url(), echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Guard: refuse to run if any Admin-role portal admin already exists.
        # Existence check only (.first(), not .scalar_one_or_none()) - more
        # than one Admin-role row can exist (users.email is intentionally
        # non-unique, so nothing prevents two), and this only needs to know
        # whether at least one is there, not fetch a single specific row.
        existing = await db.execute(
            select(User).where(User.superadmin_role == SuperAdminRole.ADMIN.value)
        )
        if existing.scalars().first() is not None:
            log.info("bootstrap.skipped", reason="admin-role portal admin already exists")
            typer.echo("INFO: An Admin-role portal admin already exists — skipping bootstrap.")
            return  # Not an error when running from startup script

        if non_interactive:
            # Read from environment variables — safe for CI/Railway one-off jobs
            email = os.environ.get("BOOTSTRAP_EMAIL", "")
            name = os.environ.get("BOOTSTRAP_NAME", "")
            password = os.environ.get("BOOTSTRAP_PASSWORD", "")
            confirm = password

            if not email or not name or not password:
                typer.echo(
                    "ERROR: --non-interactive requires BOOTSTRAP_EMAIL, BOOTSTRAP_NAME, "
                    "and BOOTSTRAP_PASSWORD environment variables to be set."
                )
                raise typer.Exit(code=1)
        else:
            # Collect credentials interactively — never pass passwords as CLI args (rule 15)
            typer.echo("Creating super admin portal user.")
            email = typer.prompt("Email")
            name = typer.prompt("Name")
            # getpass hides input so the password is never visible in terminal history
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")

        if password != confirm:
            typer.echo("ERROR: Passwords do not match.")
            raise typer.Exit(code=1)

        if len(password) < 12:
            typer.echo("ERROR: Password must be at least 12 characters.")
            raise typer.Exit(code=1)

        import uuid

        user = User(
            id=uuid.uuid4(),
            group_id=None,
            brand_id=None,
            email=email,
            password_hash=hash_password(password),
            name=name,
            superadmin_role=SuperAdminRole.ADMIN.value,
            is_active=True,
        )
        db.add(user)

        # Audit the creation — SYSTEM actor because there is no authenticated user yet
        await log_action(
            db=db,
            action=USER_CREATED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            actor_email=None,
            actor_name="bootstrap-cli",
            after_state={"email": email, "superadmin_role": SuperAdminRole.ADMIN.value},
        )

        await db.commit()

    await engine.dispose()

    log.info("bootstrap.complete", email=email)
    typer.echo(f"Super admin created: {email}")


async def _seed_all_profiles_async() -> None:
    """Seed system access profiles for every brand that is missing them."""
    engine = create_async_engine(_get_database_url(), echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(select(Brand))
        brands = result.scalars().all()

        for brand in brands:
            created = await seed_system_profiles(db, brand.id)
            if created:
                await db.commit()
                typer.echo(f"Seeded {len(created)} profile(s) for brand '{brand.name}'")

    await engine.dispose()
    typer.echo("Profile seeding complete.")


@cli.command(name="seed-all-profiles")
def seed_all_profiles() -> None:
    """Ensure every brand has its system access profiles (Admin, Reporting Only, Manager, Staff).

    Idempotent — safe to run on every startup.
    """
    asyncio.run(_seed_all_profiles_async())


@cli.command(name="bootstrap-super-admin")
def bootstrap_super_admin(
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Read credentials from BOOTSTRAP_EMAIL, BOOTSTRAP_NAME, BOOTSTRAP_PASSWORD env vars.",
    ),
) -> None:
    """
    Create the initial Admin-role portal admin.

    Interactive mode (default): prompts for email, name, and password.
    Non-interactive mode (--non-interactive): reads BOOTSTRAP_EMAIL,
    BOOTSTRAP_NAME, and BOOTSTRAP_PASSWORD from environment variables.
    Refuses to run if an Admin-role portal admin already exists.
    """
    asyncio.run(_bootstrap_super_admin_async(non_interactive=non_interactive))


async def _wipe_hierarchy_async() -> None:
    """
    Core async logic for the wipe-hierarchy command.

    Writes a SYSTEM-actor audit log row recording the pre-wipe row counts,
    then issues a single TRUNCATE ... CASCADE on groups/brands/sites. CASCADE
    removes every row in those tables and every table with a foreign key
    pointing at them (licenses, users, access_profiles, products, invoices,
    devices, etc.) regardless of each FK's own ondelete rule. audit_logs has
    no foreign key to any of these tables, so the audit trail — including
    the row this function writes — survives the wipe.
    """
    engine = create_async_engine(_get_database_url(), echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        group_count = (await db.execute(select(func.count()).select_from(Group))).scalar_one()
        brand_count = (await db.execute(select(func.count()).select_from(Brand))).scalar_one()
        site_count = (await db.execute(select(func.count()).select_from(Site))).scalar_one()

        await log_action(
            db=db,
            action=HIERARCHY_WIPED,
            entity_type="hierarchy",
            entity_id="all",
            actor_type=ActorType.SYSTEM,
            actor_name="wipe-hierarchy-cli",
            before_state={"groups": group_count, "brands": brand_count, "sites": site_count},
        )
        await db.commit()

        await db.execute(text("TRUNCATE TABLE groups, brands, sites CASCADE"))
        await db.commit()

    await engine.dispose()
    typer.echo(f"Wiped {group_count} group(s), {brand_count} brand(s), {site_count} site(s) and all dependents.")


@cli.command(name="wipe-hierarchy")
def wipe_hierarchy(
    confirm: str = typer.Option(
        "",
        "--confirm",
        help='Must be exactly "DELETE ALL" to proceed.',
    ),
) -> None:
    """
    Permanently delete every Group, Brand, and Site, plus everything that
    depends on them (Licenses, Users, access grants, products, invoices,
    devices, etc.).

    Irreversible — there is no undo. Requires --confirm "DELETE ALL" as an
    explicit safety check against accidental invocation.
    """
    if confirm != "DELETE ALL":
        typer.echo('ERROR: Refusing to run without --confirm "DELETE ALL".')
        raise typer.Exit(code=1)
    asyncio.run(_wipe_hierarchy_async())


if __name__ == "__main__":
    cli()
