"""
Shared pytest fixtures for all ZedRead tests.

Database rules (tests_CLAUDE.md):
- All tests use the real test DB (postgresql+asyncpg on port 5433, or 5432 in dev).
- Never mock the database — use real queries against the real schema.
- Each test gets an isolated session; tables are truncated after every test.
- Fixtures defined here must be used as-is — never re-create them in test files.
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base, get_db
from app.main import app

# Import all models so Base.metadata knows about them for create_all
from app.models import AuditLog, Brand, Category, Group, PortalUser, Site  # noqa: F401
from app.utils.security import create_access_token, hash_password

# ── Test database configuration ───────────────────────────────────────────────

TEST_DATABASE_URL: str = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5433/zedread_test",
)

# All table names in reverse FK dependency order — used for TRUNCATE CASCADE
_ALL_TABLES = ["audit_logs", "categories", "sites", "brands", "groups", "portal_users"]


# ── Per-test session ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped database session.

    Creates a fresh NullPool engine for each test so the asyncpg connection is
    always bound to the test's own event loop. This avoids the
    "Future attached to a different loop" error that occurs when a session-scoped
    engine is torn down in a different loop from the one that opened connections.

    Yields an active AsyncSession for the test to use.
    After the test, all rows in known tables are truncated so the next test
    starts with an empty schema.

    Yields:
        AsyncSession: An active session for the current test.
    """
    # NullPool — each connection is created and closed inline; no cross-loop sharing
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

    # Ensure schema exists (idempotent — skips tables that already exist)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

    # Truncate all tables to isolate the next test
    async with engine.begin() as conn:
        for table in _ALL_TABLES:
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

    await engine.dispose()


# ── FastAPI test client ───────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Function-scoped HTTPX async client wired to the test database session.

    Overrides the app's get_db dependency so route handlers use the same
    session as the test, allowing assertions on DB state after HTTP calls.

    Yields:
        AsyncClient: An async HTTP client targeting the test FastAPI app.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        """Dependency override that yields the shared test session."""
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Entity fixtures ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def test_group(db: AsyncSession) -> Group:
    """
    A persisted Group row for use as a parent entity in tests.

    Returns:
        Group: A saved, active Group instance.
    """
    group = Group(id=uuid.uuid4(), name="Test Group", is_active=True)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@pytest_asyncio.fixture()
async def test_brand(db: AsyncSession, test_group: Group) -> Brand:
    """
    A persisted Brand row under test_group.

    Returns:
        Brand: A saved, active Brand instance.
    """
    brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Test Brand",
        is_active=True,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


@pytest_asyncio.fixture()
async def test_site(db: AsyncSession, test_brand: Brand) -> Site:
    """
    A persisted Site row under test_brand.

    Returns:
        Site: A saved, active Site instance.
    """
    site = Site(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Test Site",
        is_active=True,
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


@pytest_asyncio.fixture()
async def test_portal_user(db: AsyncSession) -> PortalUser:
    """
    A persisted super_admin PortalUser row for use in auth-dependent tests.

    The password is 'TestPassword123!' — use portal_auth_headers to get a token.

    Returns:
        PortalUser: A saved, active super_admin portal user.
    """
    user = PortalUser(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash=hash_password("TestPassword123!"),
        name="Test Admin",
        role="super_admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture()
async def portal_auth_headers(test_portal_user: PortalUser) -> dict[str, str]:
    """
    Authorization header dict carrying a valid access token for test_portal_user.

    Returns:
        dict[str, str]: {"Authorization": "Bearer <token>"}
    """
    token = create_access_token(str(test_portal_user.id), test_portal_user.role)
    return {"Authorization": f"Bearer {token}"}
