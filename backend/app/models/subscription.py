"""
Subscription model (Step 10, Batch 10.3, requirement #1).

One row per business, linking it to a Plan and (once real Stripe billing
is configured) to Stripe's own customer/subscription records. Every
business gets one of these automatically -- on the free plan -- at
creation time (see app.services.team.create_owner_membership's sibling,
app.services.billing.create_free_subscription), and this batch's
migration backfills one for every business that existed before this
feature did, so "does this business have a subscription" is always true,
never a case the rest of the code has to handle as optional.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False, index=True
    )

    # active | trialing | past_due | canceled -- "active" covers both a
    # real paid subscription in good standing and the free plan (which
    # has no real payment lifecycle, so it's just always "active").
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Populated only once real Stripe billing is set up for this
    # business (Batch 10.3's checkout flow); both stay null on the free
    # plan indefinitely.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business")
    plan: Mapped["Plan"] = relationship("Plan")

    def __repr__(self) -> str:
        return f"<Subscription business_id={self.business_id} status={self.status}>"
