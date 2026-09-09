"""
Microsoft Graph API client (Step 11, Batch 11.9 -- Excel/OneDrive
integration).

Structured identically to app.services.google_sheets -- plain REST calls
via httpx, every function takes an already-valid access_token and never
touches stored credentials directly. See that module's docstring for
the full reasoning.

Differences from google_sheets.py, and why:
- Listing workbooks uses Graph's search endpoint filtered to the .xlsx
  extension, since (unlike Google Drive) Graph has no simple
  "mimeType=" query filter for Excel specifically.
- Reading values uses the `usedRange` endpoint, which returns exactly
  the populated rectangular region of a worksheet as a 2D array --
  Excel has no separate "worksheet dimensions" concept to query first
  the way Google Sheets' A1-notation range does, so this is the direct
  equivalent of google_sheets.fetch_sheet_values with no extra step.
"""
import logging
import re

import httpx
from openpyxl.utils.datetime import from_excel

from app.services.microsoft_oauth import MicrosoftIntegrationError

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Matches import_pipeline.MAX_ROWS's spirit and google_sheets.MAX_SHEET_ROWS
# exactly -- a generous cap on how many rows one sync reads, not a hard
# product limit. usedRange has no row-count query parameter to cap
# server-side (unlike Google's A1 range notation), so this is enforced
# by truncating the returned values client-side in fetch_worksheet_values.
MAX_SHEET_ROWS = 5020

# Bracketed sections ([Red], [$-en-US]) and quoted literal text ("units")
# in an Excel number-format code can themselves contain letters that would
# otherwise look like date/time tokens -- stripped before checking for the
# real ones. Escaped literal characters (\-, \ ) are stripped the same way.
_FORMAT_NOISE = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.')
# Excel's actual date/time tokens are lowercase (y, m, d, h, s) -- "General"
# and every plain numeric format (0.00, #,##0, 0%, etc.) contain none of
# these once the noise above is stripped out.
_DATE_TOKEN = re.compile(r"[ymdhs]")


def _is_date_number_format(number_format: str) -> bool:
    """
    Heuristic, not exhaustive -- Excel's number-format mini-language is
    large enough that no simple check covers every custom format anyone
    could construct. Deliberately biased toward over-detecting rather
    than under-detecting: a numeric value wrongly converted to an ISO
    date string, then mapped to a *non*-date field (e.g. selling_price),
    fails loudly in validate_and_convert_rows (an ISO date string like
    "2026-01-15" isn't a valid Decimal) -- a clear, correctable row
    error. Under-detecting a genuine date format is the failure mode
    this function exists to prevent: the raw serial number would
    silently misparse as a nanosecond-scale Unix timestamp, landing on
    1970-01-01 with no error at all (see this module's fetch_worksheet_
    values docstring for the full story on how this was found).
    """
    if not number_format or number_format in ("General", "@"):
        return False
    cleaned = _FORMAT_NOISE.sub("", number_format)
    return bool(_DATE_TOKEN.search(cleaned))


def _convert_date_serials(values: list[list], number_formats: list[list]) -> list[list]:
    """
    Replaces any cell whose number format marks it as a date/time with an
    ISO date string converted from Excel's underlying serial number --
    see fetch_worksheet_values's docstring for why this conversion has to
    happen here at all. Only touches cells that are both (a) flagged as
    date-formatted and (b) actually numeric (int/float) -- a cell that's
    already text (someone typed "15 Jan 2026" into a General-formatted
    cell) or already blank is left exactly as-is.
    """
    converted = []
    for row_values, row_formats in zip(values, number_formats):
        new_row = []
        for value, fmt in zip(row_values, row_formats):
            if isinstance(value, (int, float)) and not isinstance(value, bool) and _is_date_number_format(fmt):
                try:
                    new_row.append(from_excel(value).date().isoformat())
                except (ValueError, OverflowError):
                    # An out-of-range or malformed serial -- fall through
                    # to the original raw value rather than crash the
                    # whole sync; validate_and_convert_rows will surface
                    # a clean per-row error for it same as any other bad
                    # date value.
                    new_row.append(value)
            else:
                new_row.append(value)
        converted.append(new_row)
    return converted


def fetch_worksheet_values(access_token: str, workbook_item_id: str, worksheet_id: str) -> list[list]:
    """
    Raw cell values for one worksheet, as a list of rows (each a list of
    cell values) -- exactly the shape app.services.import_pipeline's
    header-detection already expects, same as
    google_sheets.fetch_sheet_values's return shape, so the exact same
    downstream parsing code handles both sources with no branching.

    usedRange (not a fixed A1-style range like Google's) returns exactly
    the populated rectangular region of the worksheet -- Graph auto-
    formats cell values as text via `usedRange(valuesOnly=true)`'s
    `text` property would lose numeric typing, so `values` (the default,
    typed) property is used instead, same reasoning as google_sheets.py
    choosing FORMATTED_VALUE for *text* cells.

    Dates need their own handling that FORMATTED_VALUE-style text does
    not, though: a cell formatted as an Excel date is, underneath,
    always a plain number (the day count from Excel's epoch) -- `values`
    returns that raw number, not a display string, confirmed against
    real-world reports of the same Graph endpoint behavior (e.g.
    Power Automate's Excel connector needing an explicit opt-in to get
    ISO-formatted dates back instead of serials). Passed straight to
    import_pipeline._parse_date_value, a raw serial like 46037 does NOT
    raise a parse error -- pandas' to_datetime silently reads a bare
    number as nanoseconds-since-Unix-epoch, landing on 1970-01-01 with
    no error at all. That's a silent wrong date on every row, for the
    single most common way Excel actually stores a date column -- so
    `numberFormat` is requested alongside `values` and any date/time-
    formatted numeric cell is converted to a proper ISO date string
    here, before anything downstream ever sees the raw serial.
    """
    data = _get(
        f"{GRAPH_BASE}/me/drive/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/usedRange",
        access_token,
        params={"$select": "values,numberFormat"},
    )
    values = data.get("values", [])
    number_formats = data.get("numberFormat", [])
    if number_formats:
        values = _convert_date_serials(values, number_formats)
    return values[:MAX_SHEET_ROWS]


def _get(url: str, access_token: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(
            url, headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=15.0
        )
    except httpx.HTTPError as exc:
        logger.warning("Network error calling %s: %s", url, exc)
        raise MicrosoftIntegrationError("Could not reach Microsoft. Please try again in a moment.") from exc

    if response.status_code == 401:
        raise MicrosoftIntegrationError("Microsoft access has expired or was revoked -- please reconnect.")
    if response.status_code == 403:
        raise MicrosoftIntegrationError(
            "Microsoft denied access to this resource -- check that the connected account can view it."
        )
    if response.status_code == 404:
        raise MicrosoftIntegrationError(
            "That workbook could not be found (it may have been deleted or moved)."
        )
    if response.status_code != 200:
        logger.warning("Microsoft Graph %s returned %s: %s", url, response.status_code, response.text)
        raise MicrosoftIntegrationError("Microsoft returned an unexpected error. Please try again.")

    return response.json()


def list_workbooks(access_token: str, limit: int = 50) -> list[dict]:
    """
    Excel workbooks the connected account can see in their OneDrive,
    most-recently-modified first. Graph's search endpoint is used
    (rather than listing an entire drive and filtering client-side)
    since it's a single request regardless of how many other files/
    folders exist in the account.
    """
    data = _get(
        f"{GRAPH_BASE}/me/drive/root/search(q='.xlsx')",
        access_token,
        params={
            "$select": "id,name,lastModifiedDateTime,file",
            "$orderby": "lastModifiedDateTime desc",
            "$top": min(limit, 100),
        },
    )
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "modified_time": item.get("lastModifiedDateTime"),
        }
        for item in data.get("value", [])
        # The search endpoint matches on filename substring, not strictly
        # the extension -- a defensive filter in case it ever returns a
        # near-match (e.g. a folder or file named "....xlsx notes.docx").
        if item.get("name", "").lower().endswith(".xlsx") and "file" in item
    ]


def list_worksheets(access_token: str, workbook_item_id: str) -> list[dict]:
    """Worksheet (tab) names and IDs within one workbook."""
    data = _get(
        f"{GRAPH_BASE}/me/drive/items/{workbook_item_id}/workbook/worksheets",
        access_token,
        params={"$select": "id,name,position,visibility"},
    )
    return [
        {"id": sheet["id"], "name": sheet["name"], "position": sheet.get("position")}
        for sheet in data.get("value", [])
        # Hidden/very-hidden worksheets are excluded -- a business's data
        # entry sheet is virtually always visible; a hidden sheet is far
        # more likely to be a scratch/calculation area not meant to be
        # imported, so surfacing it in the picker would just be noise
        # (and a likely source of confused support requests).
        if sheet.get("visibility") == "Visible"
    ]


def get_workbook_name(access_token: str, workbook_item_id: str) -> str:
    """Just the workbook's display name -- used when saving a selection so
    the UI can show a human-readable name without a second round trip later."""
    data = _get(f"{GRAPH_BASE}/me/drive/items/{workbook_item_id}", access_token, params={"$select": "name"})
    return data["name"]
