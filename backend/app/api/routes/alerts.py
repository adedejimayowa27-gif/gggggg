"""
Alert routes (Step 8 -- Business Intelligence Alert Engine).

POST /alerts/run triggers detection now (no scheduler exists in this
codebase yet -- see app.services.alert_engine's orchestrator). The rest
are plain CRUD-style read/status-update routes, all scoped through
get_owned_business the same way every other business-nested route is.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_owned_alert, get_owned_business
from app.db.session import get_db
from app.models.alert import Alert
from app.models.business import Business
from app.schemas.alert import AlertListItem, AlertOut, AlertStatus, AlertStatusUpdateIn
from app.services.alert_engine import run_all_detectors

router = APIRouter(prefix="/businesses/{business_id}/alerts", tags=["alerts"])


@router.post("/run", response_model=list[AlertOut])
def run_alert_detection(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Run every registered detector now; returns only newly-created alerts (duplicates are skipped)."""
    created = run_all_detectors(db, business)
    return [AlertOut.model_validate(a) for a in created]


@router.get("", response_model=list[AlertListItem])
def list_alerts(
    status: AlertStatus | None = Query(default=None, description="Filter by status."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    query = db.query(Alert).filter(Alert.business_id == business.id)
    if status is not None:
        query = query.filter(Alert.status == status.value)
    alerts = query.order_by(Alert.created_at.desc()).all()
    return [AlertListItem.model_validate(a) for a in alerts]


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    alert = get_owned_alert(alert_id, business, db)
    return AlertOut.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert_status(
    alert_id: uuid.UUID,
    payload: AlertStatusUpdateIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Mark read/unread, dismiss, or resolve (requirement #6)."""
    alert = get_owned_alert(alert_id, business, db)
    alert.status = payload.status.value
    if payload.status in (AlertStatus.DISMISSED, AlertStatus.RESOLVED):
        from datetime import datetime, timezone

        alert.resolved_at = datetime.now(timezone.utc)
    elif payload.status in (AlertStatus.UNREAD, AlertStatus.READ):
        alert.resolved_at = None
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)
