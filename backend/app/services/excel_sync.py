"""
Excel/OneDrive sync orchestration (Step 11, Batch 11.9 -- Excel/OneDrive
integration).

Structured identically to app.services.sheets_sync -- see that module's
docstring for the full reasoning (this is "Sync Now": ties together the
OAuth token, the Graph API client, the reader adapter, and the existing
shared import-pipeline functions into one function a route calls, and a
background job calls identically). Everything about *why* this shape is
correct is explained there; this file only calls out actual differences.

Reuses app.services.sheets_import.parse_sheet_values directly rather
than writing a parallel "excel_import.py" -- that function only ever
operates on a plain `list[list]` of raw cell values, with nothing
Google-specific in it (see its own docstring), and Microsoft Graph's
`usedRange.values` returns exactly that same shape. One adapter for
"any 2D-values API," not one per provider, despite the module's name
still saying "sheets" from when it was first written for Google Sheets
only.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ValidationError
from app.models.business import Business
from app.models.import_session import ImportSession
from app.models.microsoft_integration import MicrosoftIntegration
from app.models.transaction import Transaction
from app.services.microsoft_oauth import get_valid_access_token
from app.services.microsoft_graph import fetch_worksheet_values
from app.services.import_pipeline import compute_fingerprint, suggest_mapping, validate_and_convert_rows
from app.services.sheets_import import parse_sheet_values
from app.services.billing import check_max_transactions_this_month


def _require_selection(integration: MicrosoftIntegration) -> None:
    if not integration.workbook_item_id or not integration.worksheet_id:
        raise ValidationError(
            "No workbook/worksheet has been selected yet. Choose one before previewing or syncing."
        )


def preview_worksheet(db: Session, business: Business, integration: MicrosoftIntegration) -> tuple:
    """
    Read the currently-selected worksheet right now and suggest a column
    mapping -- nothing is persisted. Lets the user review/correct the
    mapping (reusing suggest_mapping exactly as the file importer and
    Google Sheets sync both do) before saving it with save_mapping().
    """
    _require_selection(integration)
    access_token = get_valid_access_token(db, integration)
    values = fetch_worksheet_values(access_token, integration.workbook_item_id, integration.worksheet_id)
    headers, rows = parse_sheet_values(values)
    mapping = suggest_mapping(headers)
    return headers, mapping, rows[:10], len(rows)


def save_mapping(db: Session, integration: MicrosoftIntegration, mapping: dict) -> None:
    integration.confirmed_mapping = mapping
    db.commit()


def sync_now(db: Session, business: Business, integration: MicrosoftIntegration) -> ImportSession:
    """
    The actual "Sync Now": fetch the worksheet fresh, validate every row
    through the same pipeline a file upload uses, skip rows already
    imported (by fingerprint), persist the rest, update sync metadata.

    Any failure -- expired/revoked Microsoft access, a missing/renamed
    worksheet, an unmapped required field -- is recorded onto the
    integration's last_sync_error and then re-raised, so the immediate
    HTTP response is also a clean error rather than a raw 500. Mirrors
    sheets_sync.sync_now's error handling exactly.
    """
    _require_selection(integration)
    if not integration.confirmed_mapping:
        raise ValidationError(
            "No column mapping has been saved yet. Preview the worksheet and save a mapping before syncing."
        )
    check_max_transactions_this_month(db, business)

    try:
        access_token = get_valid_access_token(db, integration)
        values = fetch_worksheet_values(
            access_token, integration.workbook_item_id, integration.worksheet_id
        )
        headers, rows = parse_sheet_values(values)
        valid_rows, row_errors = validate_and_convert_rows(rows, integration.confirmed_mapping)
    except AppError as exc:
        integration.last_sync_error = exc.message
        db.commit()
        raise

    business_id_str = str(business.id)

    # Same duplicate check as sheets_sync.sync_now and (since Batch 11.3)
    # the file-upload path -- all three now share this exact pattern.
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
        filename=f"Excel: {integration.workbook_name} / {integration.worksheet_name}",
        source="microsoft_excel",
        status="completed",
        detected_columns=headers,
        raw_rows=rows,
        suggested_mapping=suggest_mapping(headers),
        confirmed_mapping=integration.confirmed_mapping,
        total_row_count=len(rows),
        row_errors=row_errors,
    )
    db.add(import_session)
    db.flush()  # assigns import_session.id before Transactions reference it

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
        existing_fingerprints.add(fingerprint)  # guards against duplicate rows within the same worksheet/run

    import_session.imported_row_count = imported_count
    import_session.skipped_duplicate_count = skipped_count
    import_session.failed_row_count = len(row_errors)

    integration.last_synced_at = datetime.now(timezone.utc)
    integration.last_sync_error = None
    integration.status = "connected"

    db.commit()
    db.refresh(import_session)
    return import_session
