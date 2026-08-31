"""Pydantic schemas for billing (Step 10, requirement #1)."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    price_ngn: Decimal
    max_businesses_per_user: int | None
    max_branches_per_business: int | None
    max_team_members_per_business: int | None
    max_transactions_per_month: int | None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    status: str
    current_period_end: datetime | None
    plan: PlanOut


class CheckoutSessionIn(BaseModel):
    plan_key: str = Field(..., min_length=1)
    success_url: str
    cancel_url: str


class CheckoutSessionOut(BaseModel):
    checkout_url: str
