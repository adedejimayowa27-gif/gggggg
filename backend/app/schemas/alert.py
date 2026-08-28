"""
Pydantic schemas for the Business Intelligence Alert Engine (Step 8).
"""
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    alert_type: str
    severity: AlertSeverity
    title: str
    message: str
    affected_product: str | None
    affected_category: str | None
    affected_metric: str | None
    related_transaction_id: uuid.UUID | None
    period_start: date
    period_end: date
    supporting_values: dict[str, Any]
    status: AlertStatus
    resolved_at: datetime | None
    created_at: datetime


class AlertListItem(BaseModel):
    """Slimmer shape for the list endpoint -- omits supporting_values."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: str
    severity: AlertSeverity
    title: str
    message: str
    affected_product: str | None
    affected_category: str | None
    affected_metric: str | None
    status: AlertStatus
    created_at: datetime


class AlertStatusUpdateIn(BaseModel):
    """Body for PATCH .../alerts/{id} -- mark read/unread, dismiss, or resolve."""

    status: AlertStatus = Field(..., description="unread | read | dismissed | resolved")
