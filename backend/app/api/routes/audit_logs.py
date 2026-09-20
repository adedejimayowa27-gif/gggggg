"""
Audit log routes (Step 10, Batch 10.4, requirement #5).

Read-only, admin+ only -- an audit trail showing who did what is itself
sensitive (it can reveal team structure, login patterns, etc.), so
viewing it requires the same "admin" bar as managing the team.
"""
from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from app.api.deps import require_business_role
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.business import Business
from app.models.user import User
from app.schemas.audit_log import AuditLogOut

router = APIRouter(prefix="/businesses/{business_id}/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    business: Business = Depends(require_business_role("admin")),
):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.business_id == business.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    # Resolve each entry's actor_user_id to a display name (full name,
    # falling back to email) in one batch query rather than N+1 -- the
    # log previously only carried the raw UUID, which the frontend had
    # nowhere sensible to show, so "who did this" was effectively
    # missing from an audit trail whose entire purpose is who did what.
    actor_ids = {log.actor_user_id for log in logs if log.actor_user_id is not None}
    actors = {}
    if actor_ids:
        for user in db.query(User).filter(User.id.in_(actor_ids)).all():
            actors[user.id] = user.full_name or user.email

    results = []
    for log in logs:
        out = AuditLogOut.model_validate(log)
        # None covers both "no actor" (a system-initiated action) and
        # "the user who did this has since been deleted" -- the FK is
        # SET NULL on user deletion (see migration 0016), so those two
        # cases aren't distinguishable from this field alone.
        out.actor_display_name = actors.get(log.actor_user_id) if log.actor_user_id else None
        results.append(out)
    return results
