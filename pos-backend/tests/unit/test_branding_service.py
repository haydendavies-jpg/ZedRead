"""Unit tests for branding_service's logo/billing-email inheritance.

Covers:
1. Group-only — value set only at the group level resolves from "group"
2. Brand-override — a brand's own value wins over its group's
3. Site-override — a site's own value wins over both its brand and group
4. No value anywhere in the chain — resolves to (None, None)
"""

import pytest

from app.services.branding_service import resolve_effective_billing_email, resolve_effective_logo

pytestmark = pytest.mark.asyncio


# ── resolve_effective_billing_email ─────────────────────────────────────────


async def test_billing_email_resolves_from_group_only(db, test_group, test_brand, test_site):
    """When only the group has a billing_email, it resolves from 'group'."""
    test_group.billing_email = "billing@group.test"
    await db.commit()

    resolved = await resolve_effective_billing_email(db, test_site)

    assert resolved.value == "billing@group.test"
    assert resolved.source_level == "group"


async def test_billing_email_brand_overrides_group(db, test_group, test_brand, test_site):
    """A brand's own billing_email takes priority over its group's."""
    test_group.billing_email = "billing@group.test"
    test_brand.billing_email = "billing@brand.test"
    await db.commit()

    resolved = await resolve_effective_billing_email(db, test_site)

    assert resolved.value == "billing@brand.test"
    assert resolved.source_level == "brand"


async def test_billing_email_site_overrides_brand_and_group(db, test_group, test_brand, test_site):
    """A site's own billing_email takes priority over both its brand and group."""
    test_group.billing_email = "billing@group.test"
    test_brand.billing_email = "billing@brand.test"
    test_site.billing_email = "billing@site.test"
    await db.commit()

    resolved = await resolve_effective_billing_email(db, test_site)

    assert resolved.value == "billing@site.test"
    assert resolved.source_level == "site"


async def test_billing_email_resolves_to_none_when_unset_anywhere(db, test_site):
    """If no billing_email is set anywhere in the chain, value and source_level are None."""
    resolved = await resolve_effective_billing_email(db, test_site)

    assert resolved.value is None
    assert resolved.source_level is None


async def test_billing_email_resolves_directly_for_brand_entity(db, test_group, test_brand):
    """Resolving from a Brand entity (not a Site) still walks up to its Group."""
    test_group.billing_email = "billing@group.test"
    await db.commit()

    resolved = await resolve_effective_billing_email(db, test_brand)

    assert resolved.value == "billing@group.test"
    assert resolved.source_level == "group"


async def test_billing_email_resolves_directly_for_group_entity(db, test_group):
    """Resolving from a Group entity returns its own value with source_level='group'."""
    test_group.billing_email = "billing@group.test"
    await db.commit()

    resolved = await resolve_effective_billing_email(db, test_group)

    assert resolved.value == "billing@group.test"
    assert resolved.source_level == "group"


# ── resolve_effective_logo ───────────────────────────────────────────────────


async def test_logo_resolves_from_group_only(db, test_group, test_brand, test_site):
    """When only the group has a logo_url, it resolves from 'group'."""
    test_group.logo_url = "https://example.test/group-logo.png"
    await db.commit()

    resolved = await resolve_effective_logo(db, test_site)

    assert resolved.value == "https://example.test/group-logo.png"
    assert resolved.source_level == "group"


async def test_logo_brand_overrides_group(db, test_group, test_brand, test_site):
    """A brand's own logo_url takes priority over its group's."""
    test_group.logo_url = "https://example.test/group-logo.png"
    test_brand.logo_url = "https://example.test/brand-logo.png"
    await db.commit()

    resolved = await resolve_effective_logo(db, test_site)

    assert resolved.value == "https://example.test/brand-logo.png"
    assert resolved.source_level == "brand"


async def test_logo_site_overrides_brand_and_group(db, test_group, test_brand, test_site):
    """A site's own logo_url takes priority over both its brand and group."""
    test_group.logo_url = "https://example.test/group-logo.png"
    test_brand.logo_url = "https://example.test/brand-logo.png"
    test_site.logo_url = "https://example.test/site-logo.png"
    await db.commit()

    resolved = await resolve_effective_logo(db, test_site)

    assert resolved.value == "https://example.test/site-logo.png"
    assert resolved.source_level == "site"


async def test_logo_resolves_to_none_when_unset_anywhere(db, test_site):
    """If no logo_url is set anywhere in the chain, value and source_level are None."""
    resolved = await resolve_effective_logo(db, test_site)

    assert resolved.value is None
    assert resolved.source_level is None
