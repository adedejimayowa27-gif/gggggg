"""
Microsoft Excel/OneDrive integration routes (Step 11, Batch 11.9).

Mirrors app.api.routes.google_integration exactly -- same route shapes,
same reasoning for why /callback can't be behind get_owned_business (see
that module's docstring and app.services.microsoft_oauth's module
docstring for how the signed `state` parameter covers it instead).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_connected_microsoft_integration, get_owned_business, require_business_role
from app.core.config import settings
from app.db.session import get_db
from app.models.business import Business
from app.models.microsoft_integration import MicrosoftIntegration
from app.models.user import User
from app.services.audit import client_ip, log_action
from app.schemas.microsoft_integration import (
    ExcelMappingIn,
    ExcelPreviewOut,
    ExcelSelectionIn,
    ExcelSyncResultOut,
    ExcelWorksheetOut,
    MicrosoftConnectOut,
    MicrosoftIntegrationStatusOut,
    WorkbookOut,
)
from app.services.microsoft_oauth import (
    disconnect,
    exchange_code_for_tokens,
    get_authorization_url,
    get_user_email,
    get_valid_access_token,
    save_integration,
    verify_oauth_state,
)
from app.services.microsoft_graph import get_workbook_name, list_workbooks, list_worksheets
from app.services.excel_sync import preview_worksheet, save_mapping, sync_now

router = APIRouter(prefix="/businesses/{business_id}/microsoft", tags=["microsoft-integration"])

# Not business-scoped in its path, same reasoning as google_integration's
# callback_router -- Microsoft's redirect_uri is fixed and registered
# once in the app registration, so it can't contain a business_id segment.
callback_router = APIRouter(prefix="/microsoft", tags=["microsoft-integration"])

logger = logging.getLogger(__name__)


def _to_status_out(integration: MicrosoftIntegration) -> MicrosoftIntegrationStatusOut:
    """has_confirmed_mapping isn't a real column -- same reasoning as
    google_integration._to_status_out."""
    return MicrosoftIntegrationStatusOut(
        id=integration.id,
        business_id=integration.business_id,
        microsoft_email=integration.microsoft_email,
        status=integration.status,
        scopes=integration.scopes,
        workbook_item_id=integration.workbook_item_id,
        workbook_name=integration.workbook_name,
        worksheet_id=integration.worksheet_id,
        worksheet_name=integration.worksheet_name,
        has_confirmed_mapping=integration.confirmed_mapping is not None,
        last_synced_at=integration.last_synced_at,
        last_sync_error=integration.last_sync_error,
        created_at=integration.created_at,
    )


@router.get("/connect", response_model=MicrosoftConnectOut)
def connect_microsoft(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_owned_business),
):
    log_action(
        db, "microsoft_integration.connect_initiated", business_id=business.id, actor_user_id=current_user.id,
        ip_address=client_ip(request),
    )
    return MicrosoftConnectOut(authorization_url=get_authorization_url(str(business.id)))


@callback_router.get("/callback")
def microsoft_callback(
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
        logger.exception("Microsoft OAuth callback failed for business_id=%s", locals().get("business_id"))
        return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard/settings?microsoft=error")

    # No authenticated user in scope here (Microsoft's redirect carries no
    # Authorization header) -- logged with business_id only, same as
    # google_integration.google_callback.
    log_action(
        db, "microsoft_integration.connected", business_id=business.id,
        details={"microsoft_email": email},
    )

    return RedirectResponse(f"{settings.FRONTEND_URL}/dashboard/settings?microsoft=connected")


@router.get("/status", response_model=MicrosoftIntegrationStatusOut | None)
def get_microsoft_status(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    integration = (
        db.query(MicrosoftIntegration).filter(MicrosoftIntegration.business_id == business.id).first()
    )
    if not integration:
        return None
    return _to_status_out(integration)


@router.delete("", status_code=204)
def disconnect_microsoft(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    integration = get_connected_microsoft_integration(business, db)
    disconnected_email = integration.microsoft_email
    disconnect(db, integration)
    log_action(
        db, "microsoft_integration.disconnected", business_id=business.id, actor_user_id=current_user.id,
        details={"microsoft_email": disconnected_email}, ip_address=client_ip(request),
    )


@router.get("/workbooks", response_model=list[WorkbookOut])
def get_workbooks(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Excel workbooks the connected Microsoft account can see, for the user to pick from."""
    integration = get_connected_microsoft_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    return [WorkbookOut(**w) for w in list_workbooks(access_token)]


@router.get("/workbooks/{workbook_item_id}/worksheets", response_model=list[ExcelWorksheetOut])
def get_worksheets(
    workbook_item_id: str,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Worksheet (tab) names within one chosen workbook."""
    integration = get_connected_microsoft_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    return [ExcelWorksheetOut(**w) for w in list_worksheets(access_token, workbook_item_id)]


@router.put("/selection", response_model=MicrosoftIntegrationStatusOut)
def set_selection(
    payload: ExcelSelectionIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Saves which workbook + worksheet this business will sync from.
    Fetches the workbook's current name from Microsoft (rather than
    trusting a client-supplied name) so what's stored always matches
    what the connected account actually sees it as. Mirrors
    google_integration.set_selection exactly.
    """
    integration = get_connected_microsoft_integration(business, db)
    access_token = get_valid_access_token(db, integration)
    workbook_name = get_workbook_name(access_token, payload.workbook_item_id)

    worksheets = list_worksheets(access_token, payload.workbook_item_id)
    matching = next((w for w in worksheets if w["id"] == payload.worksheet_id), None)
    worksheet_name = matching["name"] if matching else payload.worksheet_id

    integration.workbook_item_id = payload.workbook_item_id
    integration.workbook_name = workbook_name
    integration.worksheet_id = payload.worksheet_id
    integration.worksheet_name = worksheet_name
    db.commit()
    db.refresh(integration)
    return _to_status_out(integration)


@router.get("/preview", response_model=ExcelPreviewOut)
def get_worksheet_preview(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Reads the currently-selected worksheet right now and suggests a
    column mapping, without importing anything -- the Excel equivalent
    of the file importer's upload-preview step.
    """
    integration = get_connected_microsoft_integration(business, db)
    headers, mapping, preview_rows, total_row_count = preview_worksheet(db, business, integration)
    return ExcelPreviewOut(
        detected_columns=headers,
        suggested_mapping=mapping,
        preview_rows=preview_rows,
        total_row_count=total_row_count,
    )


@router.put("/mapping", response_model=MicrosoftIntegrationStatusOut)
def set_mapping(
    payload: ExcelMappingIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Saves the confirmed column mapping -- every future 'Sync Now' reuses this automatically."""
    integration = get_connected_microsoft_integration(business, db)
    save_mapping(db, integration, payload.mapping)
    return _to_status_out(integration)


@router.post("/sync", response_model=ExcelSyncResultOut)
def run_sync(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_owned_business),
):
    """
    'Sync Now': re-reads the worksheet, validates every row through the
    same pipeline a file upload uses, skips already-imported rows,
    persists the rest, and returns a clear success/error summary.
    Mirrors google_integration.run_sync exactly.
    """
    integration = get_connected_microsoft_integration(business, db)
    import_session = sync_now(db, business, integration)
    log_action(
        db, "excel_sync.completed", business_id=business.id, actor_user_id=current_user.id,
        target_type="import_session", target_id=str(import_session.id),
        details={
            "imported_row_count": import_session.imported_row_count,
            "skipped_duplicate_count": import_session.skipped_duplicate_count,
            "failed_row_count": import_session.failed_row_count,
        },
        ip_address=client_ip(request),
    )
    return ExcelSyncResultOut(
        id=import_session.id,
        status=import_session.status,
        total_row_count=import_session.total_row_count,
        imported_row_count=import_session.imported_row_count or 0,
        skipped_duplicate_count=import_session.skipped_duplicate_count or 0,
        failed_row_count=import_session.failed_row_count or 0,
        row_errors=import_session.row_errors,
        synced_at=integration.last_synced_at,
    )
