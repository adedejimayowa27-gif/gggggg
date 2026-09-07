"""
Background job execution (Step 10, Batch 10.9, requirement #9).

Distinct from app.services.scheduler (which runs jobs on a recurring
*schedule* -- alert detection, Google Sheets sync): this module runs a
single job *once, immediately, off the request thread* -- for an
expensive on-demand task a route enqueues (currently: processing a
confirmed transaction import). A dedicated ThreadPoolExecutor is used
rather than reusing app.services.scheduler's APScheduler instance,
deliberately, so this module has no dependency on whether periodic jobs
are enabled (settings.ENABLE_BACKGROUND_JOBS) -- an import must still be
processable in an environment that has scheduled jobs turned off.

Each job function opens its own DB session (see _execute, same pattern
as app.services.scheduler's jobs) -- never the request-scoped session
that enqueued it, since that session is closed the moment the request
that created it returns, long before a background thread gets to run.

Adding a new background task type: write a handler function with the
signature `(db: Session, job: BackgroundJob) -> dict`, add it to
JOB_HANDLERS below, and call `enqueue_job(...)` + `run_job_async(...)`
from the route/service that needs it. Nothing else in this module
changes.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.logging_config import business_id_var, request_id_var, user_id_var
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.business import Business

logger = logging.getLogger(__name__)

# Small, bounded pool -- this app's current scale (single Render web
# service) doesn't need more concurrency than this, and an unbounded pool
# would let a burst of large-file imports exhaust DB connections instead.
# Raise this (and the DB pool size it draws from) together if it's ever
# undersized in practice.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bgjob")

JobHandler = Callable[[Session, BackgroundJob], dict]

# Populated by each service module that defines a handler (see the
# bottom of app/services/import_pipeline.py) rather than imported here,
# to avoid a circular import (import_pipeline would need to import this
# module to register, and this module importing import_pipeline back
# would create the cycle). register_handler() is the one function every
# handler-owning module calls, at import time.
JOB_HANDLERS: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    JOB_HANDLERS[job_type] = handler


def enqueue_job(
    db: Session,
    business: Business,
    job_type: str,
    payload: dict,
    actor_user_id: uuid.UUID | None = None,
) -> BackgroundJob:
    """Creates and commits a pending job row. Does not start execution --
    call run_job_async() with the returned job's id to actually run it.
    Split into two steps so a route can enqueue, commit, and only then
    submit to the executor -- guaranteeing the row is durably visible to
    a status-polling request before the background thread even starts."""
    job = BackgroundJob(
        id=uuid.uuid4(),
        business_id=business.id,
        actor_user_id=actor_user_id,
        job_type=job_type,
        status="pending",
        payload=payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_job_async(job_id: uuid.UUID) -> None:
    """Submits the job for execution on the background thread pool.
    Captures the *current* request's context (request_id/user_id/
    business_id) so the job's own log lines can still be correlated back
    to the request that triggered it, even though they're emitted on a
    different thread after this request has already returned."""
    captured_request_id = request_id_var.get()
    captured_user_id = user_id_var.get()
    captured_business_id = business_id_var.get()
    _executor.submit(
        _execute, job_id, captured_request_id, captured_user_id, captured_business_id
    )


def _execute(
    job_id: uuid.UUID,
    request_id: str | None,
    user_id: str | None,
    business_id: str | None,
) -> None:
    # Re-establish the triggering request's context on this worker thread
    # -- contextvars don't cross thread boundaries on their own, so
    # without this every log line from inside the job would show
    # request_id=None even though we know exactly which request caused it.
    request_id_var.set(request_id)
    user_id_var.set(user_id)
    business_id_var.set(business_id)

    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if job is None:
            logger.error("Background job %s not found -- cannot execute.", job_id)
            return

        handler = JOB_HANDLERS.get(job.job_type)
        if handler is None:
            job.status = "failed"
            job.error = f"No handler registered for job_type={job.job_type!r}."
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.error("No handler registered for job_type=%r (job %s).", job.job_type, job_id)
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            result = handler(db, job)
        except Exception as exc:  # noqa: BLE001 -- a handler's failure must update the row, not crash the worker thread silently
            db.rollback()
            job = db.get(BackgroundJob, job_id)  # re-fetch: the rollback above discarded the in-memory object's pending state
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.exception("Background job %s (%s) failed.", job_id, job.job_type)
            return

        job.status = "completed"
        job.result = result
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Background job %s (%s) completed.", job_id, job.job_type)
    finally:
        db.close()


def shutdown_executor(wait: bool = True) -> None:
    """Called from app.main's lifespan shutdown so an in-flight import
    isn't abandoned mid-write on a deploy/restart -- `wait=True` blocks
    shutdown until every currently-running job finishes (new submissions
    are still rejected the moment shutdown begins)."""
    _executor.shutdown(wait=wait)
