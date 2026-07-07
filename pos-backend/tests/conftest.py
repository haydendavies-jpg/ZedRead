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

import pytest
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
    EmailTemplate,
    Group,
    Invoice,
    InvoiceLineItem,
    InvoiceLineModifier,
    InvoiceTaxBreakdown,
    License,
    LicenseInvoice,
    ModifierGroup,
    ModifierOption,
    Payment,
    User,
    SuperAdmin,
    PosDevice,
    Product,
    ProductAttributeType,
    ProductAttributeValue,
    ProductComboGroup,
    ProductComboOption,
    ProductModifierGroupLink,
    ProductVariant,
    ProductVariantAttribute,
    ReportingGroup,
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

# ── Reporting view DDL ────────────────────────────────────────────────────────
# CREATE OR REPLACE VIEW so the fixture is idempotent across test runs.
# Mirrors 0010_create_reporting_views.py exactly.

_REPORTING_VIEWS = [
    """
    CREATE OR REPLACE VIEW vw_daily_sales AS
    SELECT i.brand_id, i.site_id, DATE(i.created_at) AS sale_date,
           COUNT(*) AS invoice_count,
           COALESCE(SUM(i.subtotal_cents), 0) AS subtotal_cents,
           COALESCE(SUM(i.tax_cents), 0) AS tax_cents,
           COALESCE(SUM(i.discount_cents), 0) AS discount_cents,
           COALESCE(SUM(i.total_cents), 0) AS total_cents
    FROM invoices i
    WHERE i.status = 'paid' AND i.invoice_type = 'sale'
    GROUP BY i.brand_id, i.site_id, DATE(i.created_at)
    """,
    """
    CREATE OR REPLACE VIEW vw_product_revenue AS
    SELECT ili.product_id, ili.product_name, i.brand_id, i.site_id,
           SUM(ili.quantity) AS total_units,
           COALESCE(SUM(ili.subtotal_cents), 0) AS revenue_cents,
           COALESCE(SUM(ili.tax_cents), 0) AS tax_cents
    FROM invoice_line_items ili
    JOIN invoices i ON ili.invoice_id = i.id
    WHERE i.status = 'paid' AND i.invoice_type = 'sale'
    GROUP BY ili.product_id, ili.product_name, i.brand_id, i.site_id
    """,
    """
    CREATE OR REPLACE VIEW vw_payment_methods AS
    SELECT p.method, i.brand_id, i.site_id,
           COUNT(*) AS payment_count,
           COALESCE(SUM(p.amount_cents), 0) AS total_amount_cents
    FROM payments p
    JOIN invoices i ON p.invoice_id = i.id
    WHERE i.invoice_type = 'sale'
    GROUP BY p.method, i.brand_id, i.site_id
    """,
    """
    CREATE OR REPLACE VIEW vw_tax_collected AS
    SELECT itb.tax_rate_name, itb.rate_percent, itb.tax_model, i.brand_id, i.site_id,
           COALESCE(SUM(itb.taxable_amount_cents), 0) AS taxable_amount_cents,
           COALESCE(SUM(itb.tax_amount_cents), 0) AS tax_amount_cents
    FROM invoice_tax_breakdowns itb
    JOIN invoices i ON itb.invoice_id = i.id
    WHERE i.status = 'paid' AND i.invoice_type = 'sale'
    GROUP BY itb.tax_rate_name, itb.rate_percent, itb.tax_model, i.brand_id, i.site_id
    """,
    """
    CREATE OR REPLACE VIEW vw_hourly_sales AS
    SELECT i.brand_id, i.site_id,
           EXTRACT(HOUR FROM i.created_at)::INTEGER AS hour_of_day,
           COUNT(*) AS invoice_count,
           COALESCE(SUM(i.total_cents), 0) AS total_cents
    FROM invoices i
    WHERE i.status = 'paid' AND i.invoice_type = 'sale'
    GROUP BY i.brand_id, i.site_id, EXTRACT(HOUR FROM i.created_at)
    """,
    """
    CREATE OR REPLACE VIEW vw_modifier_popularity AS
    SELECT ilm.modifier_name, i.brand_id,
           COUNT(*) AS usage_count,
           COALESCE(SUM(ilm.price_delta_cents), 0) AS total_revenue_impact_cents
    FROM invoice_line_modifiers ilm
    JOIN invoice_line_items ili ON ilm.line_item_id = ili.id
    JOIN invoices i ON ili.invoice_id = i.id
    WHERE i.status = 'paid' AND i.invoice_type = 'sale'
    GROUP BY ilm.modifier_name, i.brand_id
    """,
    """
    CREATE OR REPLACE VIEW vw_invoice_detail AS
    SELECT i.id, i.brand_id, i.site_id, i.created_by_id, i.invoice_type, i.status,
           i.subtotal_cents, i.tax_cents, i.discount_cents, i.total_cents,
           i.refund_of_id, i.is_refunded, i.voided_at, i.paid_at, i.created_at,
           s.name AS site_name, b.name AS brand_name
    FROM invoices i
    JOIN sites s ON i.site_id = s.id
    JOIN brands b ON i.brand_id = b.id
    """,
    """
    CREATE OR REPLACE VIEW vw_refund_summary AS
    SELECT i.brand_id, i.site_id, DATE(i.created_at) AS refund_date,
           COUNT(*) AS refund_count,
           COALESCE(SUM(ABS(i.total_cents)), 0) AS refund_total_cents
    FROM invoices i
    WHERE i.invoice_type = 'refund'
    GROUP BY i.brand_id, i.site_id, DATE(i.created_at)
    """,
]

# ── Test database configuration ───────────────────────────────────────────────

TEST_DATABASE_URL: str = os.getenv(
    "TEST_DATABASE_URL",
    # Port 5432 — local PostgreSQL instance (not Docker; Docker unavailable in this env).
    # Override via TEST_DATABASE_URL env var if your setup differs.
    "postgresql+asyncpg://test:test@localhost:5432/zedread_test",
)

# All table names in reverse FK dependency order — used for TRUNCATE CASCADE
_ALL_TABLES = [
    "audit_logs",
    "email_templates",
    # Stage 10 — invoices (must precede products/users they reference)
    "payments",
    "invoice_tax_breakdowns",
    "invoice_line_modifiers",
    "invoice_line_items",
    "invoices",
    "user_pos_sessions",
    "user_pins",
    "user_invites",
    "user_access_grants",
    "users",
    "access_profile_page_permissions",
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
    "tax_template_rates",
    "tax_templates",
    "tax_rates",
    "tax_categories",
    "sites",
    "brands",
    "groups",
    "superadmins",
]


# ── Per-test session ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-process auth rate limiter before/after each test.

    The limiter state is process-global, so without this reset attempts would
    accumulate across tests (all sharing one test client) and trip 429s.
    """
    from app.utils import rate_limit

    rate_limit.reset()
    yield
    rate_limit.reset()


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
        # Views are not detected by create_all — create them explicitly
        for view_sql in _REPORTING_VIEWS:
            await conn.execute(text(view_sql.strip()))

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
    group = Group(
        id=uuid.uuid4(),
        name="Test Group",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
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
    from app.services.access_profile_service import seed_system_profiles

    brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Test Brand",
        is_active=True,
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)

    # Mirrors create_brand()'s real-world invariant: every brand has its
    # system access profiles seeded, including Master User (needed by
    # site_service.create_site() when tests POST /sites/).
    await seed_system_profiles(db, brand.id)
    await db.commit()
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
        timezone="Australia/Sydney",
        currency="AUD",
        country="AU",
        address_street="1 Test Street",
        address_state="NSW",
        address_postcode="2000",
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


@pytest_asyncio.fixture()
async def test_superadmin(db: AsyncSession) -> SuperAdmin:
    """
    A persisted Admin-role SuperAdmin row for use in auth-dependent tests.

    The password is 'TestPassword123!' — use portal_auth_headers to get a token.

    Returns:
        SuperAdmin: A saved, active Admin-role portal user.
    """
    user = SuperAdmin(
        id=uuid.uuid4(),
        email="admin@test.com",
        password_hash=hash_password("TestPassword123!"),
        name="Test Admin",
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture()
async def portal_auth_headers(test_superadmin: SuperAdmin) -> dict[str, str]:
    """
    Authorization header dict carrying a valid access token for test_superadmin.

    Returns:
        dict[str, str]: {"Authorization": "Bearer <token>"}
    """
    token = create_access_token(str(test_superadmin.id), test_superadmin.role)
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
async def test_user(db: AsyncSession, test_brand: Brand) -> User:
    """
    A persisted active User row for test_brand.

    The password is 'POSPassword123!' — use pos_auth_headers to get a token.

    Returns:
        User: A saved, active User instance.
    """
    user = User(
        id=uuid.uuid4(),
        group_id=test_brand.group_id,
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
    test_user: User,
    test_site: Site,
    test_access_profile: AccessProfile,
) -> UserAccessGrant:
    """
    A persisted active UserAccessGrant linking test_user to test_site
    with test_access_profile.

    Returns:
        UserAccessGrant: A saved, active grant instance.
    """
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_user.id,
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
    db: AsyncSession,
    test_user: User,
    test_site: Site,
    test_access_grant: UserAccessGrant,
) -> dict[str, str]:
    """
    Authorization header dict carrying a valid POS access token for test_user.

    Also ensures the access grant exists (depends on test_access_grant) and
    persists a matching user_pos_sessions row so resolve_access — which now
    checks the token's jti against an active session — succeeds.

    Returns:
        dict[str, str]: {"Authorization": "Bearer <pos_access_token>"}
    """
    import uuid as _uuid
    jti = str(_uuid.uuid4())
    # Persist the active session the resolved token is validated against
    session = UserPOSSession(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        site_id=test_site.id,
        token_jti=jti,
    )
    db.add(session)
    await db.commit()
    token = create_pos_access_token(
        user_id=str(test_user.id),
        site_id=str(test_site.id),
        jti=jti,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Stage 13 fixtures ────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def test_manager_profile(db: AsyncSession, test_brand: Brand) -> AccessProfile:
    """
    A persisted Manager-like AccessProfile with can_access_portal=True for test_brand.

    Used by management auth tests.

    Returns:
        AccessProfile: A saved, portal-capable access profile.
    """
    profile = AccessProfile(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name="Manager",
        is_system=True,
        is_active=True,
        can_access_portal=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@pytest_asyncio.fixture()
async def test_portal_grant(
    db: AsyncSession,
    test_user: User,
    test_site: Site,
    test_manager_profile: AccessProfile,
) -> UserAccessGrant:
    """
    A persisted active site-scope UserAccessGrant for test_user with a
    portal-capable Manager profile.

    Used by management auth tests.

    Returns:
        UserAccessGrant: A saved, active site-scope grant.
    """
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_user.id,
        scope="site",
        site_id=test_site.id,
        brand_id=None,
        group_id=None,
        access_profile_id=test_manager_profile.id,
        granted_by_id=None,
        is_active=True,
        backend_role="admin",  # backend_role gates portal login
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


@pytest_asyncio.fixture()
async def test_brand_grant(
    db: AsyncSession,
    test_user: User,
    test_brand: Brand,
    test_manager_profile: AccessProfile,
) -> UserAccessGrant:
    """
    A persisted active brand-scope UserAccessGrant for test_user.

    Used by management auth tests for multi-grant and brand-scope scenarios.

    Returns:
        UserAccessGrant: A saved, active brand-scope grant.
    """
    grant = UserAccessGrant(
        id=uuid.uuid4(),
        user_id=test_user.id,
        scope="brand",
        site_id=None,
        brand_id=test_brand.id,
        group_id=None,
        access_profile_id=test_manager_profile.id,
        granted_by_id=None,
        is_active=True,
        backend_role="admin",  # backend_role gates portal login
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return grant


@pytest_asyncio.fixture()
async def mgmt_auth_headers(
    test_user: User,
    test_portal_grant: UserAccessGrant,
) -> dict[str, str]:
    """
    Authorization header dict carrying a valid management access token for
    test_user with a site-scope grant.

    Returns:
        dict[str, str]: {"Authorization": "Bearer <mgmt_access_token>"}
    """
    from app.utils.security import create_mgmt_access_token

    token = create_mgmt_access_token(
        user_id=str(test_user.id),
        scope=test_portal_grant.scope,
        grant_id=str(test_portal_grant.id),
        site_id=str(test_portal_grant.site_id) if test_portal_grant.site_id else None,
        brand_id=str(test_portal_grant.brand_id) if test_portal_grant.brand_id else None,
        group_id=str(test_portal_grant.group_id) if test_portal_grant.group_id else None,
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
async def test_reporting_group(db: AsyncSession, test_brand: Brand) -> ReportingGroup:
    """
    A persisted system default ReportingGroup row for test_brand.

    test_brand only seeds access profiles, not the reporting group/category
    pair create_brand() normally seeds atomically — this fixture fills that gap
    for tests that need a default reporting group to exist.

    Returns:
        ReportingGroup: A saved, system default ReportingGroup instance.
    """
    from sqlalchemy import select as _select

    result = await db.execute(
        _select(ReportingGroup).where(ReportingGroup.brand_id == test_brand.id, ReportingGroup.is_default == True)  # noqa: E712
    )
    group = result.scalar_one_or_none()
    if group is None:
        group = ReportingGroup(
            id=uuid.uuid4(),
            brand_id=test_brand.id,
            name="Default",
            is_default=True,
            is_system=True,
        )
        db.add(group)
        await db.commit()
        await db.refresh(group)
    return group


@pytest_asyncio.fixture()
async def test_product(
    db: AsyncSession, test_brand: Brand, test_site: Site, test_reporting_group: ReportingGroup
) -> Product:
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
            reporting_group_id=test_reporting_group.id,
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
        # Inclusive price; ex == inc by default so the base fixture carries no
        # embedded tax. Tax-specific tests set price_ex_cents/is_taxable directly.
        base_price_cents=1500,
        price_ex_cents=1500,
        is_taxable=True,
        display_order=0,
        is_active=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@pytest_asyncio.fixture()
async def test_billing_info_template(db: AsyncSession) -> EmailTemplate:
    """
    A persisted, active 'billing_info_request' system EmailTemplate.

    Mirrors the row seeded by migration 0029 (the `db` fixture builds the
    schema via Base.metadata.create_all rather than running migrations, so
    that seed never runs in tests — required by branding_service.request_billing_info()).

    Returns:
        EmailTemplate: A saved, active, is_system=True template.
    """
    template = EmailTemplate(
        id=uuid.uuid4(),
        template_key="billing_info_request",
        name="Billing Info Request",
        subject="Please provide billing details for $entity_name",
        body="Hi,\n\nWe need billing details for your $entity_type, $entity_name.\n\nThanks.",
        is_system=True,
        is_active=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template
