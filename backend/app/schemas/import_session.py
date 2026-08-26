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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_row_count: int
    imported_row_count: int
    failed_row_count: int
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
