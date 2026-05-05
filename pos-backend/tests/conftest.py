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
from app.models import (  # noqa: F401
    AccessProfile,
    AuditLog,
    Brand,
    Category,
    Group,
    License,
    LicenseInvoice,
    ModifierGroup,
    ModifierOption,
    POSUser,
    PortalUser,
    PosDevice,
    Product,
    ProductAttributeType,
    ProductAttributeValue,
    ProductComboGroup,
    ProductComboOption,
    ProductModifierGroupLink,
    ProductVariant,
    ProductVariantAttribute,
    Site,
    SiteProductOverride,
    SiteVariantOverride,
    TaxCategory,
    TaxRate,
    UserAccessGrant,
    UserInvite,
    UserPIN,
    UserPOSSession,
)
from app.utils.security import create_access_token, create_pos_access_token, hash_password

# ── Test database configuration ───────────────────────────────────────────────

TEST_DATABASE_URL: str = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5433/zedread_test",
)

# All table names in reverse FK dependency order — used for TRUNCATE CASCADE
_ALL_TABLES = [
    "audit_logs",
    "user_pos_sessions",
    "user_pins",
    "user_invites",
    "user_access_grants",
    "pos_users",
    "access_profiles",
    "pos_devices",
    "license_invoices",
    "licenses",
    # Stage 9 — variants, modifiers, combos (must precede products)
    "product_combo_options",
    "product_combo_groups",
    "product_modifier_group_links",
    "modifier_options",
    "modifier_groups",
    "site_variant_overrides",
    "product_variant_attributes",
    "product_variants",
    "product_attribute_values",
    "product_attribute_types",
    # Stage 8
    "site_product_overrides",
    "products",
    "categories",
    "tax_rates",
    "tax_categories",
    "sites",
    "brands",
    "groups",
    "portal_users",
]


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


@pytest_asyncio.fixture()
async def test_license(db: AsyncSession, test_site: Site) -> License:
    """
    A persisted active License row for test_site.

    Returns:
        License: A saved, active License instance.
    """
    from datetime import datetime, timezone, timedelta

    lic = License(
        id=uuid.uuid4(),
        site_id=test_site.id,
        plan_name="starter",
        status="active",
        monthly_fee_cents=9900,
        is_trial=False,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=365),
    )
    db.add(lic)
    await db.commit()
    await db.refresh(lic)
    return lic


@pytest_asyncio.fixture()
async def test_device(db: AsyncSession, test_site: Site, test_license: License) -> PosDevice:
    """
    A persisted active PosDevice row linked to test_site and test_license.

    Returns:
        PosDevice: A saved, active PosDevice instance.
    """
    device = PosDevice(
        id=uuid.uuid4(),
        site_id=test_site.id,
        license_id=test_license.id,
        device_name="Test Terminal",
        device_token="unique-test-token-abc123",
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


# ── Stage 7 fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def test_access_profile(db: AsyncSession, test_brand: Brand) -> AccessProfile:
    """
    A persisted non-system AccessProfile row for test_brand.

    Returns:
        AccessProfile: A saved, active AccessProfile instance.
    """
    profile = AccessProfile(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Cashier",
        is_system=False,
        is_active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@pytest_asyncio.fixture()
async def test_pos_user(db: AsyncSession, test_brand: Brand) -> POSUser:
    """
    A persisted active POSUser row for test_brand.

    The password is 'POSPassword123!' — use pos_auth_headers to get a token.

    Returns:
        POSUser: A saved, active POSUser instance.
    """
    user = POSUser(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Test POS User",
        email="posuser@test.com",
        password_hash=hash_password("POSPassword123!"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture()
async def test_access_grant(
    db: AsyncSession,
    test_pos_user: POSUser,
    test_site: Site,
    test_access_profile: AccessProfile,
) -> UserAccessGrant:
    """
    A persisted active UserAccessGrant linking test_pos_user to test_site
    with test_access_profile.

    Returns:
        UserAccessGrant: A saved, active grant instance.
    """
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_pos_user.id,
        site_id=test_site.id,
        access_profile_id=test_access_profile.id,
        granted_by_id=None,
        is_active=True,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


@pytest_asyncio.fixture()
async def pos_auth_headers(
    test_pos_user: POSUser,
    test_site: Site,
    test_access_grant: UserAccessGrant,
) -> dict[str, str]:
    """
    Authorization header dict carrying a valid POS access token for test_pos_user.

    Also ensures the access grant exists (depends on test_access_grant) so
    the resolve_access dependency succeeds for tests using this fixture.

    Returns:
        dict[str, str]: {"Authorization": "Bearer <pos_access_token>"}
    """
    import uuid as _uuid
    jti = str(_uuid.uuid4())
    token = create_pos_access_token(
        user_id=str(test_pos_user.id),
        site_id=str(test_site.id),
        jti=jti,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Stage 8 fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def test_tax_category(db: AsyncSession, test_brand: Brand) -> TaxCategory:
    """
    A persisted TaxCategory row for test_brand.

    Returns:
        TaxCategory: A saved, active TaxCategory instance.
    """
    tax_cat = TaxCategory(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Standard",
        is_active=True,
    )
    db.add(tax_cat)
    await db.commit()
    await db.refresh(tax_cat)
    return tax_cat


@pytest_asyncio.fixture()
async def test_product(db: AsyncSession, test_brand: Brand, test_site: Site) -> Product:
    """
    A persisted active Product row for test_brand.

    Belongs to the first category found for test_brand (the auto-seeded
    Uncategorised category created when test_brand is used in create_brand).
    Falls back to creating a direct category if none exists.

    Returns:
        Product: A saved, active Product instance.
    """
    from sqlalchemy import select as _select

    cat_result = await db.execute(
        _select(Category).where(Category.brand_id == test_brand.id).limit(1)
    )
    cat = cat_result.scalar_one_or_none()
    if cat is None:
        cat = Category(
            id=uuid.uuid4(),
            brand_id=test_brand.id,
            name="Uncategorised",
            is_system=True,
            is_active=True,
        )
        db.add(cat)
        await db.flush()

    product = Product(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        category_id=cat.id,
        tax_category_id=None,
        name="Test Burger",
        description=None,
        base_price_cents=1500,
        display_order=0,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product
