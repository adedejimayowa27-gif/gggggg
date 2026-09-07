"""
Data retention (Step 10, Batch 10.10, requirement #13).

Two unbounded-growth risks this module addresses, both storage/compliance
concerns rather than correctness bugs:

1. ImportSession.raw_rows stores a full copy of every uploaded file's
   parsed rows (up to MAX_ROWS=5000 -- see app.services.import_pipeline),
   kept indefinitely even after those rows have been validated and copied
   into Transaction rows by the import job. Once an import has finished
   (status is "completed" or "failed"), that copy has no further purpose
   -- the durable record is the Transactions it produced (or the
   row_errors already stored separately for a failed one) -- so it's
   cleared after a grace period, not the moment it finishes, in case a
   support investigation needs to look at exactly what was uploaded.

2. BackgroundJob rows (app.models.background_job) accumulate one row per
   background task ever run (currently: every confirmed import). These
   are operational/debugging records, not a compliance trail, so they're
   deleted outright after a grace period.

Deliberately NOT pruned here: AuditLog. That table is the compliance/
audit trail this app promises ("what happened and who did it") and is
kept indefinitely by design -- see docs/BACKUP_RECOVERY.md for the full
retention policy and the reasoning behind treating these two tables
differently.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.import_session import ImportSession

logger = logging.getLogger(__name__)


def prune_import_raw_rows(db: Session, retention_days: int) -> int:
    """Clears (does not delete the row -- just the raw_rows/preview data)
    finished import sessions older than the retention window. Returns the
    count cleared. Only touches sessions already in a terminal state
    ("completed"/"failed") -- "pending_mapping" (upload done, not yet
    confirmed) and "queued" (Batch 10.9's background job hasn't run yet)
    are never touched, since a user could still come back and confirm or
    is actively waiting on a result."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    # jsonb_array_length(...) > 0 -- rather than comparing the column to a
    # Python [] -- both correctly matches "not yet cleared" *and* keeps
    # this query cheap indefinitely: a session stays out of the result
    # set for good the moment it's cleared once, instead of being
    # re-matched (and re-committed as a costless no-op) every single day
    # forever just because it's still old.
    sessions = (
        db.query(ImportSession)
        .filter(
            ImportSession.status.in_(("completed", "failed")),
            ImportSession.updated_at < cutoff,
            func.jsonb_array_length(ImportSession.raw_rows) > 0,
        )
        .all()
    )
    for session in sessions:
        session.raw_rows = []
    db.commit()
    return len(sessions)


def prune_old_background_jobs(db: Session, retention_days: int) -> int:
    """Deletes BackgroundJob rows in a terminal state ("completed"/
    "failed") older than the retention window. Never touches "pending"/
    "running" rows regardless of age -- an old-but-still-running row is a
    sign something is stuck, not something to silently delete."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = (
        db.query(BackgroundJob)
        .filter(BackgroundJob.status.in_(("completed", "failed")), BackgroundJob.finished_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def run_scheduled_data_retention() -> None:
    """Called on a schedule (settings.DATA_RETENTION_INTERVAL_HOURS) from
    app.services.scheduler. Opens its own session, same pattern as every
    other scheduled job in that module -- and, same as those, isolates
    each of the two prune steps in its own try/except so one failing
    never blocks the other."""
    db: Session = SessionLocal()
    try:
        try:
            cleared = prune_import_raw_rows(db, settings.IMPORT_RAW_ROWS_RETENTION_DAYS)
            logger.info("Data retention: cleared raw_rows for %d import session(s).", cleared)
        except Exception:  # noqa: BLE001 -- must not block the job-pruning step below
            db.rollback()
            logger.exception("Data retention: pruning import raw_rows failed.")

        try:
            deleted = prune_old_background_jobs(db, settings.BACKGROUND_JOB_RETENTION_DAYS)
            logger.info("Data retention: deleted %d old background job record(s).", deleted)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Data retention: pruning background_jobs failed.")
    finally:
        db.close()
