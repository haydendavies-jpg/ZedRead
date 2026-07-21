"""Service layer for writing immutable audit log rows.

Every state-changing service function must call log_action() before committing.
This module is intentionally dependency-light — it only touches the AuditLog model
so it can be used safely from any other service without circular imports.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.statuses import ActorType
from app.models.audit_log import AuditLog

log = structlog.get_logger(__name__)


async def log_action(
    *,
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_type: ActorType = ActorType.USER,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    actor_name: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    request_id: str | None = None,
    impersonator_id: uuid.UUID | None = None,
    impersonator_email: str | None = None,
) -> AuditLog:
    """
    Create an AuditLog row and add it to the current session.

    This function does NOT call db.commit(). The caller is responsible for
    committing both the business row and the audit row in the same transaction
    so they either both persist or both roll back (CLAUDE.md absolute rule 7).

    Args:
        db: The active database session to add the row to.
        action: Dot-separated action constant from app/constants/audit_actions.py.
        entity_type: The resource type affected (e.g. 'invoice', 'product').
        entity_id: String representation of the affected entity's primary key.
        actor_type: USER for human actors, SYSTEM for automated jobs.
        actor_id: UUID of the acting user. Null when actor_type is SYSTEM.
        actor_email: Snapshotted email — preserved even if the actor changes it later.
        actor_name: Snapshotted display name at time of action.
        before_state: Serialisable dict of entity state before the change.
        after_state: Serialisable dict of entity state after the change.
        request_id: UUID from the X-Request-ID header for request correlation.
        impersonator_id: Portal admin (User) UUID when this action occurred under impersonation.
        impersonator_email: Snapshotted admin email for impersonation audit trail.

    Returns:
        AuditLog: The unsaved ORM instance added to the session.
    """
    # Validate system actor has no actor_id — system jobs are not human users
    if actor_type == ActorType.SYSTEM and actor_id is not None:
        raise ValueError("SYSTEM actor_type must not have an actor_id")

    audit_row = AuditLog(
        id=uuid.uuid4(),
        actor_id=actor_id,
        actor_type=actor_type.value,
        actor_email=actor_email,
        actor_name=actor_name,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        request_id=request_id,
        impersonator_id=impersonator_id,
        impersonator_email=impersonator_email,
    )

    db.add(audit_row)

    # DEBUG, not INFO — the audit_logs row itself is the durable record; an
    # INFO line per write duplicated it on every single mutation in production
    log.debug(
        "audit.queued",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type=actor_type.value,
        actor_id=str(actor_id) if actor_id else None,
    )

    return audit_row
