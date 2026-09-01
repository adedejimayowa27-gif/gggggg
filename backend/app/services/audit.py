"""
Audit logging service (Step 10, Batch 10.4, requirement #5).

log_action() is the one function every route/service calls to record an
important action. It is deliberately best-effort: a failure writing the
audit row (a bug in this function, a full disk, whatever) is caught and
logged to the application logger, never raised -- the actual action
being audited (inviting a team member, disconnecting Google, etc.) must
never fail *because* audit logging failed. Auditing something is always
secondary to the thing itself succeeding.

log_action() commits its own row immediately, in its own small
transaction -- it does not rely on the caller's later commit. This is
deliberate: call it only *after* the action it's recording has already
been committed successfully, never before or interleaved with it. That
ordering guarantees an audit entry only ever exists for something that
genuinely happened -- there's no window where a failed/rolled-back
action leaves behind a log entry claiming it succeeded.

Callers pass plain, JSON-safe `details` -- never a secret. This module
doesn't redact anything; it trusts callers the same way
app.models.alert.Alert's supporting_values trusts detectors, so every
call site is responsible for only including safe context (an email, a
role name, a plan key -- never a password, a token, or a full payment
card number).
"""
import logging
import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def log_action(
    db: Session,
    action: str,
    business_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    try:
        entry = AuditLog(
            id=uuid.uuid4(),
            business_id=business_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001 -- audit logging must never break the action it's recording
        logger.exception("Failed to write audit log entry for action %r", action)
        db.rollback()
