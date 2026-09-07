"""
BackgroundJob model (Step 10, Batch 10.9, requirement #9).

A generic, persisted record of one on-demand expensive task run outside
the request/response cycle (currently: processing a confirmed transaction
import; see app.services.jobs for how job_type dispatches to a handler).
Persisting the job (rather than only holding it in memory, e.g. a plain
FastAPI BackgroundTasks callback) is what makes it possible to:

- poll a job's status from a different request than the one that
  enqueued it (necessary since the enqueueing request returns
  immediately, before the work is done)
- survive an app restart/redeploy without silently losing track of a
  job that was mid-flight (the job row itself would be left "running"
  forever in that specific edge case -- acceptable for this app's scale,
  but worth knowing; a stuck "running" row past some sane timeout is a
  sign to re-enqueue, not a sign the data is corrupted)
- have an audit trail of every background task ever run for a business,
  same spirit as AuditLog but for system-initiated work rather than a
  user action

Tenant-scoped like every other business-owned resource in this app:
business_id is a required FK, and every query against this table must
filter by it (see app.api.deps's ownership-checking pattern) -- a
business must never be able to see another business's job history,
including e.g. another business's import error details.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base

# "pending" -> row created, not yet picked up by the executor.
# "running" -> a worker thread has started executing the handler.
# "completed" -> handler finished without raising; see `result`.
# "failed" -> handler raised; see `error`.
JOB_STATUSES = ("pending", "running", "completed", "failed")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    # Who triggered this job, for audit purposes -- nullable because a
    # future job_type might be system-initiated (e.g. a scheduled
    # recompute) rather than triggered by a specific user action.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Dispatch key -- see app.services.jobs.JOB_HANDLERS. e.g.
    # "import_confirm". Adding a new background task type means adding a
    # new job_type + handler, never changing this table's shape.
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    # Whatever the handler needs to do its work -- e.g. {"import_session_id":
    # "...", "mapping": {...}}. Deliberately opaque to this model; only the
    # handler named by job_type knows how to interpret it.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Populated on success -- shape is handler-specific, same reasoning as
    # payload. Null until status="completed".
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Populated on failure -- a short human-readable message, never a raw
    # stack trace (that goes to the application logs / Sentry via
    # app.core.monitoring, not into a column a business's own team members
    # might read from a "my imports" screen).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The two query patterns this table actually serves: "jobs for
        # this business, most recent first" and "find pending/running
        # jobs" (a future ops/monitoring check for stuck jobs).
        Index("ix_background_jobs_business_created", "business_id", "created_at"),
        Index("ix_background_jobs_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<BackgroundJob id={self.id} job_type={self.job_type!r} status={self.status!r}>"
