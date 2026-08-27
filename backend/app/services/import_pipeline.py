"""
Reusable transaction-import pipeline.

This module knows nothing about HTTP or the database -- it just turns
raw spreadsheet bytes (or, in the future, rows from Google Sheets/a POS
API) into a list of plain dicts, plus a suggested mapping from those
columns onto our eight standard fields (5 required-capable + 3 optional).
Keeping this separate from the route means a future data source only
needs to produce the same (headers, rows) shape to reuse everything
below.
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

import openpyxl
import pandas as pd

from app.core.exceptions import AppError

REQUIRED_FIELDS = ["date", "product", "quantity", "selling_price"]
# Batch 6.3: category, customer, and payment_method complete the 8-field
# standard schema (see Transaction model). All three are optional, same
# as cost_price -- a file that doesn't have them, or a user who leaves
# them unmapped, imports exactly as before.
STANDARD_FIELDS = [
    "date",
    "product",
    "quantity",
    "selling_price",
    "cost_price",
    "category",
    "customer",
    "payment_method",
]
OPTIONAL_FIELDS = [f for f in STANDARD_FIELDS if f not in REQUIRED_FIELDS]

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
    "category": [
        "category", "product category", "item category", "type",
        "product type", "department", "class", "product class",
    ],
    "customer": [
        "customer", "customer name", "client", "client name", "buyer",
        "bought by", "sold to", "customer id",
    ],
    "payment_method": [
        "payment method", "payment type", "payment mode", "method of payment",
        "pay method", "mode of payment", "payment",
    ],
}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 5000

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

# How many leading rows to inspect when looking for the real header row.
# Real-world exports put titles, a company name, a "Report generated on
# <date>" line, or blank spacer rows above the actual table, but that
# clutter is essentially always within the first handful of rows -- this
# is a generous buffer, not a tight guess.
HEADER_SCAN_ROWS = 20


def normalize_header(header: str) -> str:
    """Lowercase, strip, and collapse punctuation/whitespace for matching."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(header).lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _score_header_row(cells: list) -> tuple[int, int]:
    """Score how header-like one raw row is.

    Returns (synonym_matches, non_null_count). synonym_matches -- how many
    cells look like a known field name/synonym -- is the primary signal:
    a real header row has most/all of its cells recognizable as field
    names, whereas a title row ("Acme Ventures Sales Report") or a
    company-name row has at most one filled cell and no field-name
    matches at all. non_null_count is only a tie-breaker, since a data
    row can be just as densely filled as a header row.
    """
    known_terms = {syn for synonyms in FIELD_SYNONYMS.values() for syn in synonyms} | set(
        FIELD_SYNONYMS.keys()
    )

    non_null_count = 0
    synonym_matches = 0
    for cell in cells:
        if cell is None:
            continue
        text = str(cell).strip()
        if not text or text.lower() == "nan":
            continue
        non_null_count += 1
        normalized = normalize_header(text)
        if not normalized:
            continue
        if any(normalized == term or normalized in term or term in normalized for term in known_terms):
            synonym_matches += 1

    return synonym_matches, non_null_count


def _detect_header_row(preview_rows: list[list]) -> int:
    """
    Pick the most likely header row index (0-based) from a preview of raw
    rows (pandas output with header=None, so every row -- including what
    would otherwise be treated as the header -- is just data).

    Falls back to the first row with at least 2 filled cells if nothing
    scores a field-name match, and ultimately to row 0, so a well-formed
    simple file whose header is already on row 0 -- the common case --
    behaves exactly as it did before this function existed.
    """
    best_index: int | None = None
    best_score = (-1, -1)
    fallback_index: int | None = None

    for index, row in enumerate(preview_rows):
        synonym_matches, non_null_count = _score_header_row(row)
        if non_null_count == 0:
            continue  # fully blank spacer row -- never the header
        if fallback_index is None and non_null_count >= 2:
            fallback_index = index
        score = (synonym_matches, non_null_count)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index is not None and best_score[0] > 0:
        return best_index
    if fallback_index is not None:
        return fallback_index
    return 0


def _read_preview_rows_csv(file_bytes: bytes, max_rows: int) -> list[list]:
    """Read the first `max_rows` raw rows of a CSV as lists of cell
    strings, using Python's csv module instead of pandas.

    Title/company-name rows above the real header typically have far
    fewer comma-separated fields than the data rows below them (e.g. one
    cell of text vs. five data columns), which trips pandas' C-engine
    tokenizer with a hard "Expected N fields, saw M" ParserError before
    we ever get a chance to find the real header row. csv.reader makes no
    such fixed-width assumption, so it reads straight through a ragged
    file without erroring.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    rows: list[list] = []
    for index, row in enumerate(csv.reader(io.StringIO(text))):
        if index >= max_rows:
            break
        rows.append(row)
    return rows


def _read_preview_rows_xlsx(file_bytes: bytes, max_rows: int) -> list[list]:
    """Read the first `max_rows` raw rows of an .xlsx as lists of cell
    values, using openpyxl directly. Excel rows are already rectangular
    (no ragged-field issue like CSV), but reading directly here -- rather
    than via pandas -- keeps both formats going through the same
    lightweight, tolerant preview path.
    """
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows: list[list] = []
        for index, row in enumerate(sheet.iter_rows(values_only=True)):
            if index >= max_rows:
                break
            rows.append(list(row))
        return rows
    finally:
        workbook.close()


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
            preview_rows = _read_preview_rows_csv(file_bytes, HEADER_SCAN_ROWS)
        else:
            preview_rows = _read_preview_rows_xlsx(file_bytes, HEADER_SCAN_ROWS)
    except Exception as exc:  # noqa: BLE001 -- any parse failure becomes a clean 400
        raise AppError(f"Could not read file: {exc}", code="parse_error") from exc

    header_row_index = _detect_header_row(preview_rows)

    # skiprows (not header=N) so any ragged junk rows above the real
    # header -- title/company-name lines with far fewer fields than the
    # data columns -- are dropped as raw text before pandas ever tries to
    # tokenize them. Passing header=N directly would still make pandas'
    # C engine read through those same ragged lines on the way to the
    # header and can raise the same ParserError _read_preview_rows_csv
    # was written to avoid.
    try:
        if extension == ".csv":
            df = pd.read_csv(io.BytesIO(file_bytes), skiprows=header_row_index, header=0)
        else:
            df = pd.read_excel(
                io.BytesIO(file_bytes), skiprows=header_row_index, header=0, engine="openpyxl"
            )
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


def _parse_date_value(value) -> date:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("Missing date value.")
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not parse '{value}' as a date.") from exc
    if pd.isna(parsed):
        raise ValueError(f"Could not parse '{value}' as a date.")
    return parsed.date()


def _parse_decimal_value(value, field_label: str, allow_negative: bool = False) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Missing {field_label} value.")
    if isinstance(value, str):
        cleaned = re.sub(r"[^0-9.\-]", "", value)
    else:
        cleaned = str(value)
    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"'{value}' is not a valid number for {field_label}.") from exc
    if not allow_negative and parsed < 0:
        raise ValueError(f"{field_label} cannot be negative (got {value}).")
    return parsed


def validate_and_convert_rows(
    raw_rows: list[dict], mapping: dict[str, str | None]
) -> tuple[list[dict], list[dict]]:
    """
    Apply a confirmed column mapping to raw rows, validating and
    converting each one.

    Returns (valid_rows, row_errors):
    - valid_rows: list of dicts with keys date/product/quantity/
      selling_price/cost_price, ready to construct Transaction objects.
    - row_errors: list of {"row_number": int, "errors": [str, ...]},
      1-indexed against the data rows (not counting the header).
    """
    missing_required = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
    if missing_required:
        raise AppError(
            f"Missing column mapping for required field(s): {', '.join(missing_required)}.",
            code="incomplete_mapping",
        )

    valid_rows: list[dict] = []
    row_errors: list[dict] = []

    for index, raw_row in enumerate(raw_rows):
        row_number = index + 1
        errors: list[str] = []
        converted: dict = {}

        try:
            converted["date"] = _parse_date_value(raw_row.get(mapping["date"]))
        except ValueError as exc:
            errors.append(str(exc))

        product_value = raw_row.get(mapping["product"])
        product_str = str(product_value).strip() if product_value is not None else ""
        if not product_str:
            errors.append("Product is required.")
        else:
            converted["product"] = product_str

        try:
            converted["quantity"] = _parse_decimal_value(
                raw_row.get(mapping["quantity"]), "quantity"
            )
            if converted["quantity"] <= 0:
                errors.append("Quantity must be greater than zero.")
        except ValueError as exc:
            errors.append(str(exc))

        try:
            converted["selling_price"] = _parse_decimal_value(
                raw_row.get(mapping["selling_price"]), "selling price"
            )
        except ValueError as exc:
            errors.append(str(exc))

        cost_column = mapping.get("cost_price")
        if cost_column:
            cost_raw = raw_row.get(cost_column)
            if cost_raw is not None and str(cost_raw).strip():
                try:
                    converted["cost_price"] = _parse_decimal_value(cost_raw, "cost price")
                except ValueError as exc:
                    errors.append(str(exc))
            else:
                converted["cost_price"] = None
        else:
            converted["cost_price"] = None

        if errors:
            row_errors.append({"row_number": row_number, "errors": errors})
        else:
            valid_rows.append(converted)

    return valid_rows, row_errors
