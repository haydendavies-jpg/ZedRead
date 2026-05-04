"""Celery tasks for license lifecycle management.

The expiry task runs nightly and marks licenses as expired when their
expires_at timestamp has passed. It uses actor_type=SYSTEM because no
human user triggers it — the audit log must reflect an automated actor.
"""

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app
from app.constants.audit_actions import LICENSE_EXPIRED
from app.constants.statuses import ActorType, LicenseStatus
from app.models.license import License
from app.services.audit_service import log_action

log = structlog.get_logger(__name__)


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Create a fresh async engine and session factory for use inside a Celery task.

    NullPool is used so each task invocation gets its own connection that is
    closed when the task finishes — Celery workers run in separate processes
    and must not share connection pools with the main API process.

    Returns:
        async_sessionmaker: Factory that yields AsyncSession instances.
    """
    import os
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/zedread",
    )
    engine = create_async_engine(database_url, echo=False, poolclass=NullPool)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _run_expire_overdue_licenses() -> int:
    """
    Query and expire all licenses where expires_at < now() and status = active.

    Each expired license is updated in its own transaction so a single failure
    does not roll back the whole batch.

    Returns:
        int: Number of licenses expired in this run.
    """
    session_factory = _get_session_factory()
    expired_count = 0
    now = datetime.now(tz=timezone.utc)

    async with session_factory() as db:
        result = await db.execute(
            select(License).where(
                License.status == LicenseStatus.ACTIVE.value,
                License.expires_at < now,
            )
        )
        licenses = list(result.scalars().all())

    log.info("license_expiry.found", count=len(licenses))

    for lic in licenses:
        try:
            # Each license gets its own transaction — isolate per-row failures
            async with session_factory() as db:
                # Re-fetch inside this session to attach to the current transaction
                fresh_result = await db.execute(select(License).where(License.id == lic.id))
                fresh_lic = fresh_result.scalar_one()

                # Guard against race: another worker may have already expired this one
                if fresh_lic.status != LicenseStatus.ACTIVE.value:
                    continue

                fresh_lic.status = LicenseStatus.EXPIRED.value

                await log_action(
                    db=db,
                    action=LICENSE_EXPIRED,
                    entity_type="license",
                    entity_id=str(fresh_lic.id),
                    actor_type=ActorType.SYSTEM,  # No human actor — automated nightly job
                    actor_id=None,
                    before_state={"status": LicenseStatus.ACTIVE.value},
                    after_state={"status": LicenseStatus.EXPIRED.value},
                )

                await db.commit()
                expired_count += 1
                log.info("license.expired", license_id=str(fresh_lic.id))
        except Exception:
            log.error("license_expiry.row_failed", license_id=str(lic.id), exc_info=True)
            raise  # Re-raise per rule 14 — never swallow exceptions silently

    return expired_count


@celery_app.task(name="app.tasks.license_tasks.expire_overdue_licenses")
def expire_overdue_licenses() -> int:
    """
    Celery entry point: expire all overdue active licenses.

    Delegates to the async implementation via asyncio.run() because Celery
    task functions are synchronous but the database layer is async.

    Returns:
        int: Number of licenses expired in this run.
    """
    log.info("license_expiry.starting")
    count = asyncio.run(_run_expire_overdue_licenses())
    log.info("license_expiry.finished", expired_count=count)
    return count
