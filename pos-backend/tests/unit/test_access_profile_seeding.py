"""Unit tests for access profile seeding.

Covers:
1. Happy path — 4 profiles created for a new brand
2. Idempotency — calling seed twice does not create duplicates
3. Partial seed — only missing profiles are created
4. Correct metadata — all seeded profiles are system profiles and active
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.statuses import SystemAccessProfile
from app.models.access_profile import AccessProfile
from app.services.access_profile_service import seed_system_profiles

pytestmark = pytest.mark.asyncio


async def test_seed_creates_four_profiles(db, test_brand):
    """Seeding a brand creates exactly 4 system access profiles."""
    created = await seed_system_profiles(db, test_brand.id)
    await db.commit()

    assert len(created) == 4
    names = {p.name for p in created}
    assert names == {p.value for p in SystemAccessProfile}


async def test_seeded_profiles_have_correct_metadata(db, test_brand):
    """All seeded profiles are marked is_system=True and is_active=True."""
    await seed_system_profiles(db, test_brand.id)
    await db.commit()

    result = await db.execute(
        select(AccessProfile).where(AccessProfile.brand_id == test_brand.id)
    )
    profiles = result.scalars().all()

    assert len(profiles) == 4
    for profile in profiles:
        assert profile.is_system is True
        assert profile.is_active is True
        assert profile.brand_id == test_brand.id


async def test_seed_is_idempotent(db, test_brand):
    """Calling seed_system_profiles twice on the same brand creates no duplicates."""
    await seed_system_profiles(db, test_brand.id)
    await db.commit()

    second_run = await seed_system_profiles(db, test_brand.id)
    await db.commit()

    # Second call should return empty list — all already exist
    assert second_run == []

    result = await db.execute(
        select(AccessProfile).where(AccessProfile.brand_id == test_brand.id)
    )
    profiles = result.scalars().all()
    assert len(profiles) == 4  # Still exactly 4, not 8


async def test_seed_only_creates_missing_profiles(db, test_brand):
    """If some profiles already exist, only the missing ones are created."""
    # Pre-create one profile manually
    existing = AccessProfile(
        id=uuid.uuid4(),
        brand_id=test_brand.id,
        name=SystemAccessProfile.ADMIN.value,
        is_system=True,
        is_active=True,
    )
    db.add(existing)
    await db.commit()

    created = await seed_system_profiles(db, test_brand.id)
    await db.commit()

    # Only the remaining 3 should be created
    assert len(created) == 3
    created_names = {p.name for p in created}
    assert SystemAccessProfile.ADMIN.value not in created_names

    # Total in DB should still be 4
    result = await db.execute(
        select(AccessProfile).where(AccessProfile.brand_id == test_brand.id)
    )
    assert len(result.scalars().all()) == 4


async def test_seed_does_not_affect_other_brands(db, test_brand, test_group):
    """Seeding one brand does not create profiles for another brand."""
    from app.models.brand import Brand

    other_brand = Brand(
        id=uuid.uuid4(),
        group_id=test_group.id,
        name="Other Brand",
        is_active=True,
    )
    db.add(other_brand)
    await db.commit()

    await seed_system_profiles(db, test_brand.id)
    await db.commit()

    result = await db.execute(
        select(AccessProfile).where(AccessProfile.brand_id == other_brand.id)
    )
    assert result.scalars().all() == []
