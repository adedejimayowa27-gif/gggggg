"""
Pydantic schemas for the Microsoft Excel/OneDrive integration (Step 11,
Batch 11.9).

Mirrors app.schemas.google_integration exactly -- same "never include a
token field, anywhere" rule enforced at the API boundary. See that
module's docstring.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MicrosoftConnectOut(BaseModel):
    """Response for GET /microsoft/connect -- the URL the frontend redirects the browser to."""

    authorization_url: str


class MicrosoftIntegrationStatusOut(BaseModel):
    """
    Everything the frontend is allowed to know about a business's
    Microsoft connection. No token, ever.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    microsoft_email: str
    status: str
    scopes: str
    workbook_item_id: str | None
    workbook_name: str | None
    worksheet_id: str | None
    worksheet_name: str | None
    has_confirmed_mapping: bool
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime


class WorkbookOut(BaseModel):
    id: str
    name: str
    modified_time: str | None = None


class ExcelWorksheetOut(BaseModel):
    id: str
    name: str
    position: int | None = None


class ExcelSelectionIn(BaseModel):
    workbook_item_id: str = Field(..., min_length=1)
    worksheet_id: str = Field(..., min_length=1)


class ExcelPreviewOut(BaseModel):
    """
    Response for GET .../microsoft/preview -- same idea as SheetPreviewOut
    (Google Sheets): shows what the currently-selected worksheet looks
    like right now, so the user can review/correct the mapping before
    saving it. Nothing is persisted yet.
    """

    detected_columns: list[str]
    suggested_mapping: dict[str, str | None]
    preview_rows: list[dict]
    total_row_count: int


class ExcelMappingIn(BaseModel):
    mapping: dict[str, str | None]


class ExcelSyncRowError(BaseModel):
    row_number: int
    errors: list[str]


class ExcelSyncResultOut(BaseModel):
    """Response for POST .../microsoft/sync -- mirrors SyncResultOut (Google Sheets) exactly."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_row_count: int
    imported_row_count: int
    skipped_duplicate_count: int
    failed_row_count: int
    row_errors: list[ExcelSyncRowError]
    synced_at: datetime
