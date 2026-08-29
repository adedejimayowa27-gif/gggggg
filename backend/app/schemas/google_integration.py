"""
Pydantic schemas for the Google Sheets integration (Step 9).

Deliberately never includes any token field, anywhere -- that's what
enforces requirement #2 at the API boundary, not just at the model layer.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GoogleConnectOut(BaseModel):
    """Response for GET /google/connect -- the URL the frontend redirects the browser to."""

    authorization_url: str


class GoogleIntegrationStatusOut(BaseModel):
    """
    Everything the frontend is allowed to know about a business's Google
    connection. No token, ever.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    google_email: str
    status: str
    scopes: str
    spreadsheet_id: str | None
    spreadsheet_name: str | None
    worksheet_title: str | None
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime
