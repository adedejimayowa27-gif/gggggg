"""
Pydantic schemas for the Google Sheets integration (Step 9).

Deliberately never includes any token field, anywhere -- that's what
enforces requirement #2 at the API boundary, not just at the model layer.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    has_confirmed_mapping: bool
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime


class SpreadsheetOut(BaseModel):
    id: str
    name: str
    modified_time: str | None = None


class WorksheetOut(BaseModel):
    title: str
    sheet_id: int
    row_count: int | None = None
    column_count: int | None = None


class SelectionIn(BaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    worksheet_title: str = Field(..., min_length=1)


class SheetPreviewOut(BaseModel):
    """
    Response for GET .../google/preview -- same idea as
    ImportPreviewOut (Step 6's file upload), but nothing is persisted
    yet: this just shows what the currently-selected worksheet looks
    like right now, so the user can review/correct the mapping before
    saving it.
    """

    detected_columns: list[str]
    suggested_mapping: dict[str, str | None]
    preview_rows: list[dict]
    total_row_count: int


class MappingIn(BaseModel):
    mapping: dict[str, str | None]


class SyncRowError(BaseModel):
    row_number: int
    errors: list[str]


class SyncResultOut(BaseModel):
    """Response for POST .../google/sync -- requirement #9's success/error/import summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_row_count: int
    imported_row_count: int
    skipped_duplicate_count: int
    failed_row_count: int
    row_errors: list[SyncRowError]
    synced_at: datetime
