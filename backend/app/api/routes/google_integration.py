"""
Google integration routes (Step 9, Batch 9.1).

/connect and /status and DELETE are normal authenticated, business-owned
routes. /callback is the one exception: Google redirects the user's
browser here directly with no Authorization header, so it can't be
behind get_owned_business -- see app.services.google_oauth's module
docstring for how the signed `state` parameter covers that instead.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.google_integration import GoogleIntegration
from app.schemas.google_integration import GoogleConnectOut, GoogleIntegrationStatusOut
from app.services.google_oauth import (
    exchange_code_for_tokens,
    get_authorization_url,
    get_user_email,
    revoke_and_delete,
    save_integration,
    verify_oauth_state,
)

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
    integration = db.query(GoogleIntegration).filter(GoogleIntegration.business_id == business.id).first()
    if not integration:
        raise NotFoundError("No Google connection found for this business.")
    revoke_and_delete(db, integration)
