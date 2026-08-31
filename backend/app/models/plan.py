"""
Plan model (Step 10, Batch 10.3, requirement #1).

Plans live in the database (not hardcoded constants) so limits can be
adjusted without a deploy -- e.g. raising a free-tier cap, or adding a
new paid tier, is a data change, not a code change.

The seed "free" plan (created by this batch's migration) is deliberately
generous -- see that migration's docstring for why: this app already has
real usage before billing tiers existed, and the free tier's limits must
not retroactively break anything anyone is already doing.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Stable machine-readable identifier (e.g. "free", "starter", "pro")
    # -- used in code to look up a specific plan; `name` is just display text.
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Monthly price in Naira (0 for the free plan). Decimal, matching how
    # this app represents every other currency amount.
    price_ngn: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    # Usage limits enforced by app.services.billing.check_usage_limit.
    # NULL on any of these means "unlimited" -- used for the free plan's
    # transaction cap so existing usage is never retroactively capped
    # until a real limit is deliberately configured.
    max_businesses_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_branches_per_business: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_team_members_per_business: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_transactions_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stripe's price identifier for this plan, once real Stripe billing
    # is configured (Batch 10.3's checkout route needs this to know what
    # to charge for). Null until set.
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Plan key={self.key!r} name={self.name!r}>"
