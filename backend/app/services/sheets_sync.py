"""
Google Sheets sync orchestration (Step 9, Batch 9.4).

This is "Sync Now": ties together the OAuth token (9.1), the Sheets API
client (9.2), the reader adapter (9.3), and the existing shared
import-pipeline functions (suggest_mapping, validate_and_convert_rows,
compute_fingerprint -- all from Batches 6/9.3, untouched here) into one
function that a route can call, and that a future background job could
call identically with no changes (requirement #10).

Every sync re-fetches the sheet fresh and re-runs full validation --
never assumes the sheet's structure hasn't changed since last time
(requirement #11). Duplicate rows (already-imported, matched by
fingerprint) are silently skipped rather than re-inserted or erroring
(requirement #7). Every sync is recorded as its own ImportSession
(source="google_sheets") so it shows up in the same import history a
file upload would, and its Transactions are reachable through the same
import_session_id relationship (requirement #12 -- one pipeline, not two).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ValidationError
from app.models.business import Business
from app.models.google_integration import GoogleIntegration
from app.models.import_session import ImportSession
from app.models.transaction import Transaction
from app.services.google_oauth import get_valid_access_token
from app.services.google_sheets import fetch_sheet_values
from app.services.import_pipeline import compute_fingerprint, suggest_mapping, validate_and_convert_rows
from app.services.sheets_import import parse_sheet_values


def _require_selection(integration: GoogleIntegration) -> None:
    if not integration.spreadsheet_id or not integration.worksheet_title:
        raise ValidationError(
            "No spreadsheet/worksheet has been selected yet. Choose one before previewing or syncing."
        )


def preview_sheet(db: Session, business: Business, integration: GoogleIntegration) -> tuple:
    """
    Read the currently-selected worksheet right now and suggest a column
    mapping -- nothing is persisted. Lets the user review/correct the
    mapping (requirement #4, reusing suggest_mapping exactly as the file
    importer does) before saving it with save_mapping().
    """
    _require_selection(integration)
    access_token = get_valid_access_token(db, integration)
    values = fetch_sheet_values(access_token, integration.spreadsheet_id, integration.worksheet_title)
    headers, rows = parse_sheet_values(values)
    mapping = suggest_mapping(headers)
    return headers, mapping, rows[:10], len(rows)


def save_mapping(db: Session, integration: GoogleIntegration, mapping: dict) -> None:
    integration.confirmed_mapping = mapping
    db.commit()


def sync_now(db: Session, business: Business, integration: GoogleIntegration) -> ImportSession:
    """
    The actual "Sync Now": fetch the sheet fresh, validate every row
    through the same pipeline a file upload uses, skip rows already
    imported (by fingerprint), persist the rest, update sync metadata.

    Any failure -- expired/revoked Google access, a missing/renamed
    worksheet, an unmapped required field -- is recorded onto the
    integration's last_sync_error (so the UI can show what went wrong on
    the *next* status check) and then re-raised, so the immediate HTTP
    response is also a clean error rather than a raw 500.
    """
    _require_selection(integration)
    if not integration.confirmed_mapping:
        raise ValidationError(
            "No column mapping has been saved yet. Preview the sheet and save a mapping before syncing."
        )

    try:
        access_token = get_valid_access_token(db, integration)
        values = fetch_sheet_values(access_token, integration.spreadsheet_id, integration.worksheet_title)
        headers, rows = parse_sheet_values(values)
        valid_rows, row_errors = validate_and_convert_rows(rows, integration.confirmed_mapping)
    except AppError as exc:
        integration.last_sync_error = exc.message
        db.commit()
        raise

    business_id_str = str(business.id)

    # Requirement #7: skip rows already imported. Fingerprints are
    # computed for every valid row up front so the "already exists"
    # lookup is a single query, not one query per row.
    fingerprints = [compute_fingerprint(business_id_str, row) for row in valid_rows]
    existing_fingerprints = {
        row[0]
        for row in db.query(Transaction.fingerprint)
        .filter(Transaction.business_id == business.id, Transaction.fingerprint.in_(fingerprints))
        .all()
    }

    import_session = ImportSession(
        id=uuid.uuid4(),
        business_id=business.id,
        filename=f"Google Sheets: {integration.spreadsheet_name} / {integration.worksheet_title}",
        source="google_sheets",
        status="completed",
        detected_columns=headers,
        raw_rows=rows,
        suggested_mapping=suggest_mapping(headers),
        confirmed_mapping=integration.confirmed_mapping,
        total_row_count=len(rows),
        row_errors=row_errors,
    )
    db.add(import_session)
    db.flush()  # assigns import_session.id's row before Transactions reference it

    imported_count = 0
    skipped_count = 0
    for row, fingerprint in zip(valid_rows, fingerprints):
        if fingerprint in existing_fingerprints:
            skipped_count += 1
            continue
        db.add(
            Transaction(
                business_id=business.id,
                import_session_id=import_session.id,
                fingerprint=fingerprint,
                **row,
            )
        )
        imported_count += 1
        existing_fingerprints.add(fingerprint)  # guards against duplicate rows within the same sheet/run

    import_session.imported_row_count = imported_count
    import_session.skipped_duplicate_count = skipped_count
    import_session.failed_row_count = len(row_errors)

    integration.last_synced_at = datetime.now(timezone.utc)
    integration.last_sync_error = None
    integration.status = "connected"

    db.commit()
    db.refresh(import_session)
    return import_session
