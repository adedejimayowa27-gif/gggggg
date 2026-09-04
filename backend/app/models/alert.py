"""
Alert model (Step 8 -- Business Intelligence Alert Engine).

Represents one detected event for a business (e.g. "unusually low sales
in the last 7 days" or "Rice cost price jumped 20%"). Alerts are written
only by app.services.alert_engine's detectors -- this model is pure
storage, same relationship the Simulation model has with
scenario_engine.

Design choices:

- `alert_type` is a plain string key (e.g. "low_sales",
  "falling_profit_margin"), not a DB enum -- same reasoning as
  Simulation.scenario_type: new alert types (req #12) are a code change
  in the detector registry, not a migration.
- `severity` and `status` ARE fixed, small sets (LOW/MEDIUM/HIGH/CRITICAL;
  unread/read/dismissed/resolved) enforced at the schema layer as Python
  enums -- unlike alert_type, these aren't expected to grow, so a bit of
  DB-level looseness (still plain String columns, for simplicity) costs
  nothing.
- `supporting_values` is JSONB for the same reason Simulation.parameters
  is: different detectors need different evidence (a z-score and a
  baseline mean for a statistical detector; a before/after price for a
  cost-change detector). Always backend-computed -- never populated from
  an LLM response.
- `dedupe_key` identifies "the same underlying event" (alert_type + scope
  + period bucket) so re-running detection doesn't spam duplicate rows.
  Enforcement (skip insert if an active alert with this key already
  exists) lives in the orchestrator (Batch 8.4), not a DB constraint here
  -- a dismissed alert's event legitimately recurring later should be
  allowed to raise a new one.
- `related_transaction_id` is nullable and only set by detectors that
  genuinely point at one specific transaction (e.g. a single unusual
  outlier row); most alerts are period/aggregate-based and leave it null.
"""
import uuid
from datetime import date as date_type, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # e.g. "low_sales" | "high_sales" | "revenue_change" | "profit_change"
    # | "falling_profit_margin" | "fast_growing_product" |
    # "slow_moving_product" | "stock_shortage" | "cost_change" |
    # "unusual_transaction_pattern" | "forecast_revenue_decline" -- see
    # app.services.alert_engine's detector registry.
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # LOW | MEDIUM | HIGH | CRITICAL
    severity: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Linking fields (requirement #8) -- populated where a detector's
    # finding genuinely points at one of these; left null otherwise.
    affected_product: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_metric: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # The historical window the detector's finding is based on.
    period_start: Mapped[date_type] = mapped_column(Date, nullable=False)
    period_end: Mapped[date_type] = mapped_column(Date, nullable=False)

    # Backend-computed evidence: baseline mean/stddev, observed value,
    # deviation, thresholds used, etc. -- whatever the specific detector
    # needs to justify this alert. Never written from an LLM response.
    supporting_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # unread | read | dismissed | resolved
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="unread", index=True)

    # Identifies "the same underlying event" for duplicate prevention
    # (requirement #5) -- see this module's docstring.
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} type={self.alert_type!r} severity={self.severity} status={self.status}>"
