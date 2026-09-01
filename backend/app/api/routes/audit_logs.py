"""Pydantic schema for audit log entries (Step 10, requirement #5)."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime
