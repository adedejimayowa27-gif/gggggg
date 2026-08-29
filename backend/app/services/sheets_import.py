"""
Google Sheets reader adapter (Step 9, Batch 9.3).

The one job of this module: turn raw Sheets cell values into exactly the
(headers, rows) shape app.services.import_pipeline.parse_upload already
produces from a CSV/XLSX file. Once that shape exists, everything else
-- suggest_mapping, validate_and_convert_rows, error handling -- is the
same shared pipeline calling the exact same functions, not a parallel
implementation. This is what "reuse the existing transaction-import
pipeline" and "do not create a separate system" mean concretely: a
Sheets row and a CSV row become indistinguishable the moment they leave
this module.

Header detection is reused directly from import_pipeline rather than
reimplemented -- _detect_header_row already operates on plain nested
lists (list of rows, each a list of cell values), which is exactly what
the Sheets API returns, so there was nothing Sheets-specific to write
there at all.
"""
from app.core.exceptions import AppError
from app.services.import_pipeline import HEADER_SCAN_ROWS, MAX_ROWS, _detect_header_row, _json_safe


def _normalize_cell(value):
    """Sheets represents a truly blank interior cell as "" (an empty
    string), whereas a CSV's blank cell comes through pandas as NaN ->
    None. Normalizing "" to None here means validate_and_convert_rows'
    existing blank-checks (`if raw is not None and str(raw).strip()`)
    behave identically regardless of source."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return _json_safe(value)


def _rows_to_dicts(header_row: list, data_rows: list[list]) -> tuple[list[str], list[dict]]:
    """
    Builds (headers, rows) from a known header row and the data rows
    beneath it. Sheets trims trailing blank cells per-row (a row can be
    shorter than the header row if its rightmost columns are empty), so
    missing trailing cells are padded with None rather than dropped --
    every row dict always has every header as a key, same guarantee
    parse_upload's pandas-based path provides.
    """
    headers = [
        str(cell).strip() if cell not in (None, "") else f"Column_{i + 1}"
        for i, cell in enumerate(header_row)
    ]
    rows = []
    for raw_row in data_rows:
        row_dict = {}
        for i, header in enumerate(headers):
            raw_value = raw_row[i] if i < len(raw_row) else None
            row_dict[header] = _normalize_cell(raw_value)
        rows.append(row_dict)
    return headers, rows


def parse_sheet_values(values: list[list]) -> tuple[list[str], list[dict]]:
    """
    Parse raw Sheets values (as returned by
    app.services.google_sheets.fetch_sheet_values) into (headers, rows),
    detecting the real header row exactly like a messy file upload would
    -- a spreadsheet with a title row, a company name, or blank rows
    above the real table works the same way a messy CSV does.

    Raises AppError for the same classes of problem parse_upload raises
    for: an empty sheet, or more data rows than this app supports per
    import.
    """
    if not values:
        raise AppError("This worksheet has no data.", code="empty_file")

    preview = values[:HEADER_SCAN_ROWS]
    header_row_index = _detect_header_row(preview)

    header_row = values[header_row_index]
    data_rows = values[header_row_index + 1 :]

    if not data_rows:
        raise AppError("This worksheet has no data rows.", code="empty_file")
    if len(data_rows) > MAX_ROWS:
        raise AppError(
            f"Worksheet has too many rows. Maximum supported is {MAX_ROWS} rows per sync.",
            code="too_many_rows",
        )

    return _rows_to_dicts(header_row, data_rows)
