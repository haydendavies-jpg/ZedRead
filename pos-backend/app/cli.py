"""Management CLI for ZedRead POS.

Run with: python -m app.cli <command>

Commands:
  bootstrap-super-admin   Create the initial super_admin portal user.
                          Refuses to run if a super_admin already exists.
"""

import asyncio
import getpass

import structlog
import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.constants.audit_actions import PORTAL_USER_CREATED
from app.constants.statuses import ActorType, PortalUserRole
from app.logging_config import configure_logging
from app.models.portal_user import PortalUser
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

    Creates the first super_admin portal user.
    Exits with an error if a super_admin already exists to prevent duplicates.

    Args:
        non_interactive: When True, reads BOOTSTRAP_EMAIL, BOOTSTRAP_NAME,
                         BOOTSTRAP_PASSWORD from environment instead of prompting.
    """
    import os

    engine = create_async_engine(_get_database_url(), echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Guard: refuse to run if any super_admin already exists
        existing = await db.execute(
            select(PortalUser).where(PortalUser.role == PortalUserRole.SUPER_ADMIN.value)
        )
        if existing.scalar_one_or_none() is not None:
            log.info("bootstrap.skipped", reason="super_admin already exists")
            typer.echo("INFO: A super_admin already exists — skipping bootstrap.")
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

        user = PortalUser(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(password),
            name=name,
            role=PortalUserRole.SUPER_ADMIN.value,
            is_active=True,
        )
        db.add(user)

        # Audit the creation — SYSTEM actor because there is no authenticated user yet
        await log_action(
            db=db,
            action=PORTAL_USER_CREATED,
            entity_type="portal_user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            actor_email=None,
            actor_name="bootstrap-cli",
            after_state={"email": email, "role": PortalUserRole.SUPER_ADMIN.value},
        )

        await db.commit()

    await engine.dispose()

    log.info("bootstrap.complete", email=email)
    typer.echo(f"Super admin created: {email}")


@cli.command(name="bootstrap-super-admin")
def bootstrap_super_admin(
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Read credentials from BOOTSTRAP_EMAIL, BOOTSTRAP_NAME, BOOTSTRAP_PASSWORD env vars.",
    ),
) -> None:
    """
    Create the initial super_admin portal user.

    Interactive mode (default): prompts for email, name, and password.
    Non-interactive mode (--non-interactive): reads BOOTSTRAP_EMAIL,
    BOOTSTRAP_NAME, and BOOTSTRAP_PASSWORD from environment variables.
    Refuses to run if a super_admin already exists.
    """
    asyncio.run(_bootstrap_super_admin_async(non_interactive=non_interactive))


if __name__ == "__main__":
    cli()
