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
    # Populated by the route (not from the ORM object -- it's not a
    # column on AuditLog) with the acting user's name or email, so the
    # frontend has something human-readable to show instead of a raw
    # UUID. None means either a system-initiated action or a user who
    # has since been deleted -- these aren't distinguishable from this
    # field alone.
    actor_display_name: str | None = None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    ip_address: str | None
    created_at: datetime
