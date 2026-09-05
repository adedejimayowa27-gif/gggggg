"""
Background job scheduler (Step 10, Batch 10.7, requirements #9, #10).

In-process scheduler (APScheduler's BackgroundScheduler, thread-based) --
no separate worker service or message broker needed, which fits this
app's current single Render web service. Each job function opens its
own DB session (never reuses a request-scoped one) and wraps each
business/integration individually in try/except so one failure never
stops the rest of the batch.

Known limitation, same as app.core.rate_limit's in-memory storage: if
this app ever runs multiple instances/processes, each would run these
jobs independently and redundantly. That's wasteful (repeated API calls,
repeated queries) but not harmful -- alert detection's dedupe_key and
the Sheets sync's transaction fingerprints already prevent any duplicate
data from actually being created. Upgrading to a real task queue
(Celery+Redis, or a dedicated Render cron job/worker) would be the fix
if that scale is ever reached.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import Business
from app.models.google_integration import GoogleIntegration
from app.services.alert_engine import run_all_detectors
from app.services.sheets_sync import sync_now

logger = logging.getLogger(__name__)


def run_scheduled_alert_detection() -> None:
    """Runs every registered alert detector for every business. Called on a schedule
    (settings.ALERT_DETECTION_INTERVAL_HOURS) -- same underlying function
    POST /alerts/run calls, just with no HTTP request behind it."""
    db: Session = SessionLocal()
    try:
        businesses = db.query(Business).all()
        created_total = 0
        for business in businesses:
            try:
                created = run_all_detectors(db, business)
                created_total += len(created)
            except Exception:  # noqa: BLE001 -- one business's failure must not stop the rest
                logger.exception("Scheduled alert detection failed for business %s", business.id)
        logger.info(
            "Scheduled alert detection complete: %d businesses checked, %d new alerts created",
            len(businesses), created_total,
        )
    finally:
        db.close()


def run_scheduled_google_sync() -> None:
    """Syncs every business with a connected, fully-configured Google
    integration (a spreadsheet/worksheet selected AND a mapping saved --
    anything less isn't ready to sync unattended). Same underlying
    sync_now() function POST /sync calls."""
    db: Session = SessionLocal()
    try:
        integrations = (
            db.query(GoogleIntegration)
            .filter(
                GoogleIntegration.status == "connected",
                GoogleIntegration.confirmed_mapping.isnot(None),
            )
            .all()
        )
        synced_count = 0
        for integration in integrations:
            business = db.query(Business).filter(Business.id == integration.business_id).first()
            if not business:
                continue
            try:
                sync_now(db, business, integration)
                synced_count += 1
            except Exception:  # noqa: BLE001 -- one integration's failure must not stop the rest
                logger.exception(
                    "Scheduled Google Sheets sync failed for business %s", business.id
                )
        logger.info(
            "Scheduled Google Sheets sync complete: %d/%d integrations synced",
            synced_count, len(integrations),
        )
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler | None:
    """Called once, from app.main's lifespan startup. No-op (returns None)
    if settings.ENABLE_BACKGROUND_JOBS is False."""
    global _scheduler
    if not settings.ENABLE_BACKGROUND_JOBS:
        logger.info("Background jobs disabled (ENABLE_BACKGROUND_JOBS=false) -- scheduler not started.")
        return None

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_scheduled_alert_detection,
        "interval",
        hours=settings.ALERT_DETECTION_INTERVAL_HOURS,
        id="alert_detection",
    )
    scheduler.add_job(
        run_scheduled_google_sync,
        "interval",
        hours=settings.GOOGLE_SYNC_INTERVAL_HOURS,
        id="google_sync",
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Background job scheduler started (alerts every %dh, Sheets sync every %dh).",
        settings.ALERT_DETECTION_INTERVAL_HOURS, settings.GOOGLE_SYNC_INTERVAL_HOURS,
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
