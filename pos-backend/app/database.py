"""SQLAlchemy async engine, session factory, Base, and get_db dependency."""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


# Read from environment; falls back to local Docker default for development
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://zedread:zedread@localhost:5432/zedread",
)

# Single engine instance shared across the application lifetime.
# statement_cache_size=0 is required when using Supabase's Transaction pooler
# (PgBouncer in transaction mode), which does not support asyncpg prepared statements.
#
# Pool sizing is env-tunable so a deployment can hold more warm connections
# open — establishing a fresh TLS connection to a remote pooler costs several
# network round trips, which shows up as multi-second first-byte latency when
# the API and database are in different regions.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # Warm connections kept open between requests (SQLAlchemy default is 5)
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    # Extra connections allowed under burst load beyond pool_size
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    # Proactively recycle connections before the pooler's idle timeout can
    # kill them server-side — a killed connection costs a failed round trip
    # (pre_ping) plus a full reconnect on the next request that draws it
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
    connect_args={"statement_cache_size": 0},
)

# Session factory — each request gets its own session via get_db()
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep ORM objects usable after commit without re-query
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy ORM models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request.

    The session is always closed after the request completes, even on error.
    Callers are responsible for committing — this dependency does not auto-commit.

    Yields:
        AsyncSession: An active database session bound to the request lifecycle.
    """
    async with AsyncSessionLocal() as session:
        yield session
