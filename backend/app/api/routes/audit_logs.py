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
    return [AuditLogOut.model_validate(log) for log in logs]
