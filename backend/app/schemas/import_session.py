"""
Pydantic schemas for the transaction-import pipeline (upload, preview,
confirm, and import history).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportPreviewOut(BaseModel):
    """Returned immediately after upload: the parsed preview + suggested mapping."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    detected_columns: list[str]
    suggested_mapping: dict[str, str | None]
    preview_rows: list[dict]
    total_row_count: int


class RowError(BaseModel):
    row_number: int
    errors: list[str]


class ImportConfirmIn(BaseModel):
    mapping: dict[str, str | None]


class ImportConfirmOut(BaseModel):
    """
    Batch 10.9: imported_row_count/failed_row_count are now nullable --
    both stay null while status is "queued" (the background job hasn't
    run yet), get populated once status becomes "completed" or "failed".
    Same shape used for both the immediate 202 response from POST
    .../confirm and the polling GET .../{import_id} response, so the
    frontend can treat them identically.

    Batch 11.3: added skipped_duplicate_count, for parity with
    SyncResultOut (Google Sheets sync) -- file uploads now run the same
    fingerprint-based duplicate check Sheets sync always has, so the
    count needs somewhere to surface.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_row_count: int
    imported_row_count: int | None
    skipped_duplicate_count: int | None
    failed_row_count: int | None
    row_errors: list[RowError]


class ImportSessionOut(BaseModel):
    """Used for the import-history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    total_row_count: int
    imported_row_count: int | None
    failed_row_count: int | None
    created_at: datetime
