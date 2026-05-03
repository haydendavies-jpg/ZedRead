"""Alembic environment — configures async engine and imports all models for autogenerate."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base and all models so autogenerate detects table changes
from app.database import Base
import app.models  # noqa: F401 — side-effect import registers all models with Base

# Alembic Config object provides access to alembic.ini values
config = context.config

# Wire Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate comparison
target_metadata = Base.metadata

# Read DATABASE_URL from env var; fall back to alembic.ini value
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    config.get_main_option("sqlalchemy.url", ""),
)


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (no live DB connection needed).

    Emits SQL to stdout. Useful for reviewing migration SQL before applying.
    """
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """
    Execute migrations against a live connection.

    Args:
        connection: An active SQLAlchemy connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode against a real async database connection.

    asyncpg requires the async engine path — the standard sync engine will not
    work with postgresql+asyncpg URLs.
    """
    connectable = create_async_engine(DATABASE_URL)

    async with connectable.connect() as connection:
        # run_sync wraps the sync Alembic migration runner inside the async context
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
