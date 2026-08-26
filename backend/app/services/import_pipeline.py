"""
Reusable transaction-import pipeline.

This module knows nothing about HTTP or the database -- it just turns
raw spreadsheet bytes (or, in the future, rows from Google Sheets/a POS
API) into a list of plain dicts, plus a suggested mapping from those
columns onto our five standard fields. Keeping this separate from the
route means a future data source only needs to produce the same
(headers, rows) shape to reuse everything below.
"""
import io
import re
from decimal import Decimal
from datetime import date, datetime

import pandas as pd

from app.core.exceptions import AppError

STANDARD_FIELDS = ["date", "product", "quantity", "selling_price", "cost_price"]

# Known header variants for each standard field, used for automatic
# column-mapping suggestions. Add more synonyms here as real-world files
# reveal new naming patterns -- this list is the whole point of "handle
# different column names intelligently".
FIELD_SYNONYMS: dict[str, list[str]] = {
    "date": [
        "date", "transaction date", "sale date", "order date",
        "txn date", "purchase date", "invoice date",
    ],
    "product": [
        "product", "item", "item name", "product name", "sku",
        "description", "product description", "item description",
    ],
    "quantity": [
        "quantity", "qty", "qty sold", "units", "units sold",
        "amount sold", "quantity sold",
    ],
    "selling_price": [
        "selling price", "sale price", "price", "unit price",
        "sales price", "revenue per unit", "selling price per unit",
    ],
    "cost_price": [
        "cost price", "cost", "unit cost", "cogs", "purchase price",
        "cost per unit",
    ],
}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 5000

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


def normalize_header(header: str) -> str:
    """Lowercase, strip, and collapse punctuation/whitespace for matching."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(header).lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """
    Suggest which uploaded column corresponds to each standard field.

    Returns a dict like {"date": "Transaction Date", "product": "Item Name",
    ...} using the *original* header text as the value, so the frontend can
    show it back to the user unchanged. Fields with no confident match are
    set to None and left for the user to map manually.
    """
    normalized_headers = {h: normalize_header(h) for h in headers}
    mapping: dict[str, str | None] = {field: None for field in STANDARD_FIELDS}
    used_headers: set[str] = set()

    # Pass 1: exact match against known synonyms.
    for field in STANDARD_FIELDS:
        for original, normalized in normalized_headers.items():
            if original in used_headers:
                continue
            if normalized in FIELD_SYNONYMS[field]:
                mapping[field] = original
                used_headers.add(original)
                break

    # Pass 2: loose "contains" match for anything still unmapped, e.g. a
    # header like "Total Qty" contains "qty" even though it's not an exact
    # synonym match.
    for field in STANDARD_FIELDS:
        if mapping[field] is not None:
            continue
        for original, normalized in normalized_headers.items():
            if original in used_headers:
                continue
            if any(syn in normalized for syn in FIELD_SYNONYMS[field]):
                mapping[field] = original
                used_headers.add(original)
                break

    return mapping


def _json_safe(value):
    """Convert a pandas/numpy cell value into something JSON-serializable."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and pd.isna(value):
        return None
    # numpy scalar types (int64, float64, bool_) -> native Python types
    if hasattr(value, "item"):
        return value.item()
    return value


def parse_upload(file_bytes: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """
    Parse an uploaded .csv or .xlsx file into (headers, rows).

    Raises AppError for anything that would otherwise surface as an
    unhandled 500 -- oversized files, wrong extensions, unparseable
    content, or empty sheets.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise AppError(
            f"File is too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
            code="file_too_large",
        )

    lower_name = filename.lower()
    extension = next((ext for ext in ALLOWED_EXTENSIONS if lower_name.endswith(ext)), None)
    if extension is None:
        raise AppError(
            "Unsupported file type. Please upload a .csv or .xlsx file.",
            code="unsupported_file_type",
        )

    try:
        if extension == ".csv":
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 -- any parse failure becomes a clean 400
        raise AppError(f"Could not read file: {exc}", code="parse_error") from exc

    if df.empty:
        raise AppError("The uploaded file has no data rows.", code="empty_file")

    if len(df) > MAX_ROWS:
        raise AppError(
            f"File has too many rows. Maximum supported is {MAX_ROWS} rows per import.",
            code="too_many_rows",
        )

    headers = [str(col) for col in df.columns]
    df = df.where(pd.notnull(df), None)
    rows = [
        {header: _json_safe(row[i]) for i, header in enumerate(headers)}
        for row in df.itertuples(index=False, name=None)
    ]

    return headers, rows
