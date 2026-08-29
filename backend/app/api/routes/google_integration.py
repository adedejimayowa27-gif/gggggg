"""
Google integration routes (Step 9).

/connect and /status and DELETE (Batch 9.1) are normal authenticated,
business-owned routes. /callback is the one exception: Google redirects
the user's browser here directly with no Authorization header, so it
can't be behind get_owned_business -- see app.services.google_oauth's
module docstring for how the signed `state` parameter covers that
instead. /spreadsheets, /spreadsheets/{id}/worksheets, and /selection
(Batch 9.2) let the user pick which sheet/tab to import from once
connected.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_connected_google_integration, get_owned_business
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.google_integration import GoogleIntegration
from app.schemas.google_integration import (
    GoogleConnectOut,
    GoogleIntegrationStatusOut,
    MappingIn,
    SelectionIn,
    SheetPreviewOut,
    SpreadsheetOut,
    SyncResultOut,
    WorksheetOut,
)
from app.services.google_oauth import (
    exchange_code_for_tokens,
    get_authorization_url,
    get_user_email,
    get_valid_access_token,
    revoke_and_delete,
    save_integration,
    verify_oauth_state,
)
from app.services.google_sheets import get_spreadsheet_title, list_spreadsheets, list_worksheets
from app.services.sheets_sync import preview_sheet, save_mapping, sync_now

router = APIRouter(prefix="/businesses/{business_id}/google", tags=["google-integration"])

# Not business-scoped in its path (Google's redirect_uri is fixed and
# registered once in Google Cloud Console, so it can't contain a
# business_id segment) -- kept in this same file since it's the other
# half of the same OAuth flow.
callback_router = APIRouter(prefix="/google", tags=["google-integration"])


@router.get("/connect", response_model=GoogleConnectOut)
def connect_google(business: Business = Depends(get_owned_business)):
    return GoogleConnectOut(authorization_url=get_authorization_url(str(business.id)))


@callback_router.get("/callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        business_id = verify_oauth_state(state)
        business = db.query(Business).filter(Business.id == uuid.UUID(business_id)).first()
        if not business:
            raise ValueError("business not found")

        tokens = exchange_code_for_tokens(code)
        email = get_user_email(tokens["access_token"])
        save_integration(db, business, tokens, email)
    except Exception:  # noqa: BLE001 -- any failure in this flow redirects with an error flag, never a raw error response
        return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard/settings?google=error")

    return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard/settings?google=connected")


@router.get("/status", response_model=GoogleIntegrationStatusOut | None)
def get_google_status(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    integration = db.query(GoogleIntegration).filter(GoogleIntegration.business_id == business.id).first()
    if not integration:
        return None
    return GoogleIntegrationStatusOut.model_validate(integration)


@router.delete("", status_code=204)
def disconnect_google(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    integration = get_connected_google_integration(business, db)
    revoke_and_delete(db, integration)


@router.get("/spreadsheets", response_model=list[SpreadsheetOut])
def get_spreadsheets(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Spreadsheets the connected Google account can see, for the user to pick from."""
    integration = get_connected_google_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    return [SpreadsheetOut(**s) for s in list_spreadsheets(access_token)]


@router.get("/spreadsheets/{spreadsheet_id}/worksheets", response_model=list[WorksheetOut])
def get_worksheets(
    spreadsheet_id: str,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Worksheet (tab) titles within one chosen spreadsheet."""
    integration = get_connected_google_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    return [WorksheetOut(**w) for w in list_worksheets(access_token, spreadsheet_id)]


@router.put("/selection", response_model=GoogleIntegrationStatusOut)
def set_selection(
    payload: SelectionIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Saves which spreadsheet + worksheet this business will sync from.
    Fetches the spreadsheet's current title from Google (rather than
    trusting a client-supplied name) so what's stored always matches
    what the connected account actually sees it as.
    """
    integration = get_connected_google_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    spreadsheet_name = get_spreadsheet_title(access_token, payload.spreadsheet_id)

    integration.spreadsheet_id = payload.spreadsheet_id
    integration.spreadsheet_name = spreadsheet_name
    integration.worksheet_title = payload.worksheet_title
    db.commit()
    db.refresh(integration)
    return GoogleIntegrationStatusOut.model_validate(integration)


@router.get("/preview", response_model=SheetPreviewOut)
def get_sheet_preview(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Reads the currently-selected worksheet right now and suggests a
    column mapping, without importing anything -- the Sheets equivalent
    of the file importer's upload-preview step (requirement #4).
    """
    integration = get_connected_google_integration(business, db)
    headers, mapping, preview_rows, total_row_count = preview_sheet(db, business, integration)
    return SheetPreviewOut(
        detected_columns=headers,
        suggested_mapping=mapping,
        preview_rows=preview_rows,
        total_row_count=total_row_count,
    )


@router.put("/mapping", response_model=GoogleIntegrationStatusOut)
def set_mapping(
    payload: MappingIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Saves the confirmed column mapping -- every future 'Sync Now' reuses this automatically."""
    integration = get_connected_google_integration(business, db)
    save_mapping(db, integration, payload.mapping)
    return GoogleIntegrationStatusOut.model_validate(integration)


@router.post("/sync", response_model=SyncResultOut)
def run_sync(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    'Sync Now' (requirement #9): re-reads the sheet, validates every row
    through the same pipeline a file upload uses, skips already-imported
    rows, persists the rest, and returns a clear success/error summary.
    """
    integration = get_connected_google_integration(business, db)
    import_session = sync_now(db, business, integration)
    return SyncResultOut(
        id=import_session.id,
        status=import_session.status,
        total_row_count=import_session.total_row_count,
        imported_row_count=import_session.imported_row_count or 0,
        skipped_duplicate_count=import_session.skipped_duplicate_count or 0,
        failed_row_count=import_session.failed_row_count or 0,
        row_errors=import_session.row_errors,
        synced_at=integration.last_synced_at,
    )
