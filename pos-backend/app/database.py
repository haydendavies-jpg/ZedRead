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

# Single engine instance shared across the application lifetime
engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # Set True locally to log all SQL (too noisy for prod)
    pool_pre_ping=True,  # Verify connections before use to handle stale pool entries
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
