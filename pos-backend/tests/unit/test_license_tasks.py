"""Unit tests for the license expiry Celery task.

Tests run against the real test DB — no mocking per tests_CLAUDE.md rule 10.
The async helper function is called directly so we can assert DB state without
needing a live Celery worker.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.constants.audit_actions import LICENSE_EXPIRED
from app.constants.statuses import LicenseStatus
from app.models.audit_log import AuditLog
from app.models.license import License
from app.tasks.license_tasks import _run_expire_overdue_licenses


@pytest.fixture()
def _patched_session_factory(db, monkeypatch):
    """
    Patch _get_session_factory() so the task uses the test DB session.

    The task creates its own engine via _get_session_factory(). We replace that
    function to return a factory that yields the test session, so the task's
    DB writes are visible in the test's transaction.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from unittest.mock import AsyncMock, MagicMock
    import contextlib

    # Build a minimal async context manager that yields the test db session
    class _FakeFactory:
        """Minimal async_sessionmaker replacement that returns the test session."""

        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass  # Don't close the test session

    monkeypatch.setattr(
        "app.tasks.license_tasks._get_session_factory",
        lambda: _FakeFactory(),
    )


async def test_expire_overdue_licenses_marks_expired(db, test_site, _patched_session_factory):
    """Overdue active license is set to expired and an audit row is written."""
    lic = License(
        id=uuid.uuid4(),
        site_id=test_site.id,
        plan_name="starter",
        status=LicenseStatus.ACTIVE.value,
        monthly_fee_cents=9900,
        is_trial=False,
        starts_at=datetime.now(tz=timezone.utc) - timedelta(days=400),
        expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1),  # Already expired
    )
    db.add(lic)
    await db.commit()

    count = await _run_expire_overdue_licenses()

    assert count >= 1

    await db.refresh(lic)
    assert lic.status == LicenseStatus.EXPIRED.value

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == str(lic.id),
            AuditLog.action == LICENSE_EXPIRED,
        )
    )
    row = result.scalar_one()
    assert row.actor_type == "system"
    assert row.actor_id is None
    assert row.after_state["status"] == LicenseStatus.EXPIRED.value


async def test_expire_overdue_licenses_skips_future_licenses(db, test_site, _patched_session_factory):
    """A license with a future expires_at is NOT expired by the task."""
    lic = License(
        id=uuid.uuid4(),
        site_id=test_site.id,
        plan_name="pro",
        status=LicenseStatus.ACTIVE.value,
        monthly_fee_cents=0,
        is_trial=True,
        starts_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=100),  # Not yet expired
    )
    db.add(lic)
    await db.commit()

    await _run_expire_overdue_licenses()

    await db.refresh(lic)
    assert lic.status == LicenseStatus.ACTIVE.value


async def test_expire_overdue_licenses_skips_already_disabled(db, test_site, _patched_session_factory):
    """A disabled (not active) license is not touched even if overdue."""
    lic = License(
        id=uuid.uuid4(),
        site_id=test_site.id,
        plan_name="starter",
        status=LicenseStatus.DISABLED.value,
        monthly_fee_cents=0,
        is_trial=False,
        starts_at=datetime.now(tz=timezone.utc) - timedelta(days=400),
        expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1),
    )
    db.add(lic)
    await db.commit()

    await _run_expire_overdue_licenses()

    await db.refresh(lic)
    assert lic.status == LicenseStatus.DISABLED.value
