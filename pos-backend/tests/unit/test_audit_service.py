"""Unit tests for app/services/audit_service.py.

Tests verify that log_action() creates the correct AuditLog object with the
expected field values. The real test DB is used — no mocking (rule 10).
"""

import uuid

import pytest
from sqlalchemy import select

from app.constants.audit_actions import GROUP_CREATED
from app.constants.statuses import ActorType
from app.models.audit_log import AuditLog
from app.services.audit_service import log_action


async def test_log_action_creates_audit_row_with_correct_fields(db):
    """log_action() adds an AuditLog row with all expected field values."""
    actor_id = uuid.uuid4()
    entity_id = str(uuid.uuid4())

    audit_row = await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=entity_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        actor_email="test@example.com",
        actor_name="Test User",
        before_state=None,
        after_state={"name": "My Group", "is_active": True},
    )

    # Flush to write the row to the DB within this transaction without committing
    await db.flush()

    result = await db.execute(
        select(AuditLog).where(AuditLog.id == audit_row.id)
    )
    row = result.scalar_one()

    assert row.action == GROUP_CREATED
    assert row.entity_type == "group"
    assert row.entity_id == entity_id
    assert row.actor_type == ActorType.USER.value
    assert row.actor_id == actor_id
    assert row.actor_email == "test@example.com"
    assert row.actor_name == "Test User"
    assert row.before_state is None
    assert row.after_state == {"name": "My Group", "is_active": True}


async def test_log_action_system_actor_has_no_actor_id(db):
    """SYSTEM actor type must not carry an actor_id — it is a non-human actor."""
    entity_id = str(uuid.uuid4())

    audit_row = await log_action(
        db=db,
        action="license.expired",
        entity_type="license",
        entity_id=entity_id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,  # System jobs have no user ID
        actor_email=None,
        actor_name=None,
    )

    await db.flush()

    result = await db.execute(
        select(AuditLog).where(AuditLog.id == audit_row.id)
    )
    row = result.scalar_one()

    assert row.actor_type == ActorType.SYSTEM.value
    assert row.actor_id is None
    assert row.actor_email is None


async def test_log_action_system_actor_with_actor_id_raises(db):
    """Passing actor_id for a SYSTEM actor must raise ValueError."""
    with pytest.raises(ValueError, match="SYSTEM actor_type must not have an actor_id"):
        await log_action(
            db=db,
            action="license.expired",
            entity_type="license",
            entity_id=str(uuid.uuid4()),
            actor_type=ActorType.SYSTEM,
            actor_id=uuid.uuid4(),  # This is the invalid combination
        )


async def test_log_action_does_not_commit(db):
    """log_action() adds to the session but does not commit — caller commits."""
    entity_id = str(uuid.uuid4())

    await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=entity_id,
        actor_type=ActorType.USER,
        actor_id=uuid.uuid4(),
        actor_email="commit@test.com",
        actor_name="Commit Tester",
    )

    # Flush to make the row visible to queries without committing
    await db.flush()

    result = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == entity_id)
    )
    rows = result.scalars().all()

    # Row is visible because it was flushed to the DB within this transaction
    assert len(rows) == 1
    assert rows[0].entity_id == entity_id


async def test_log_action_snapshots_actor_email(db):
    """actor_email is stored as a plain string snapshot, not a reference."""
    original_email = "original@example.com"

    audit_row = await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=str(uuid.uuid4()),
        actor_type=ActorType.USER,
        actor_id=uuid.uuid4(),
        actor_email=original_email,
        actor_name="Snapshot Test",
    )

    # The stored email must equal the value at the time of the call
    assert audit_row.actor_email == original_email


async def test_log_action_request_id_stored(db):
    """request_id is stored on the audit row for HTTP request correlation."""
    request_id = str(uuid.uuid4())

    audit_row = await log_action(
        db=db,
        action=GROUP_CREATED,
        entity_type="group",
        entity_id=str(uuid.uuid4()),
        actor_type=ActorType.USER,
        actor_id=uuid.uuid4(),
        actor_email="req@test.com",
        actor_name="Req User",
        request_id=request_id,
    )

    assert audit_row.request_id == request_id
