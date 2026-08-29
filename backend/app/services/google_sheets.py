"""
Google Sheets/Drive API client (Step 9, Batch 9.2).

Plain REST calls via httpx, same style as app.services.google_oauth --
Drive API v3 and Sheets API v4 are both ordinary JSON-over-HTTP APIs, so
this avoids pulling in google-api-python-client's much heavier
dependency chain for what's just two authenticated GET requests.

Every function here takes an already-valid access_token (the caller is
expected to have gone through get_valid_access_token first) and never
touches stored credentials directly -- this module only knows how to
talk to Google once handed a token, not how to obtain or refresh one.
"""
import logging

import httpx

from app.services.google_oauth import GoogleIntegrationError

logger = logging.getLogger(__name__)

DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
SHEETS_SPREADSHEET_ENDPOINT = "https://sheets.googleapis.com/v4/spreadsheets"


def _get(url: str, access_token: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(
            url, headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=15.0
        )
    except httpx.HTTPError as exc:
        logger.warning("Network error calling %s: %s", url, exc)
        raise GoogleIntegrationError("Could not reach Google. Please try again in a moment.") from exc

    if response.status_code == 401:
        raise GoogleIntegrationError("Google access has expired or was revoked -- please reconnect.")
    if response.status_code == 403:
        raise GoogleIntegrationError(
            "Google denied access to this resource -- check that the connected account can view it."
        )
    if response.status_code == 404:
        raise GoogleIntegrationError("That spreadsheet could not be found (it may have been deleted or moved).")
    if response.status_code != 200:
        logger.warning("Google API %s returned %s: %s", url, response.status_code, response.text)
        raise GoogleIntegrationError("Google returned an unexpected error. Please try again.")

    return response.json()


def list_spreadsheets(access_token: str, limit: int = 50) -> list[dict]:
    """
    Spreadsheets the connected account can see, most-recently-modified
    first. Uses Drive's file listing (not the Sheets API, which has no
    "list all my spreadsheets" endpoint of its own) filtered to just the
    Google Sheets mimetype, and explicitly excludes trashed files.
    """
    data = _get(
        DRIVE_FILES_ENDPOINT,
        access_token,
        params={
            "q": "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            "fields": "files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": min(limit, 100),
        },
    )
    return [
        {"id": f["id"], "name": f["name"], "modified_time": f.get("modifiedTime")}
        for f in data.get("files", [])
    ]


def list_worksheets(access_token: str, spreadsheet_id: str) -> list[dict]:
    """Worksheet (tab) titles and row/column counts within one spreadsheet."""
    data = _get(
        f"{SHEETS_SPREADSHEET_ENDPOINT}/{spreadsheet_id}",
        access_token,
        params={"fields": "properties.title,sheets.properties"},
    )
    return [
        {
            "title": sheet["properties"]["title"],
            "sheet_id": sheet["properties"]["sheetId"],
            "row_count": sheet["properties"].get("gridProperties", {}).get("rowCount"),
            "column_count": sheet["properties"].get("gridProperties", {}).get("columnCount"),
        }
        for sheet in data.get("sheets", [])
    ]


def get_spreadsheet_title(access_token: str, spreadsheet_id: str) -> str:
    """Just the spreadsheet's display name -- used when saving a selection so
    the UI can show a human-readable name without a second round trip later."""
    data = _get(
        f"{SHEETS_SPREADSHEET_ENDPOINT}/{spreadsheet_id}",
        access_token,
        params={"fields": "properties.title"},
    )
    return data["properties"]["title"]
