"""
Microsoft OAuth service (Step 11, Batch 11.9 -- Excel/OneDrive
integration).

Structured identically to app.services.google_oauth -- same
responsibilities (consent URL, code exchange, token refresh, encrypt/
decrypt at rest, read/write the integration row), same security posture
(encrypted tokens, signed state token, never exposed to any schema). See
that module's docstring for the full reasoning; this one only calls out
where Microsoft's identity platform differs from Google's.

Differences from google_oauth.py, and why:
- Uses the "common" tenant endpoint (not a single-tenant one), so both
  personal Microsoft accounts (outlook.com, hotmail.com) and work/school
  (Microsoft 365) accounts can connect -- "Microsoft Excel" as a product
  spans both, and there's no reason to arbitrarily exclude either.
- No token-revocation endpoint call on disconnect: unlike Google's
  simple POST /revoke, Microsoft's v2.0 endpoint has no equivalent
  single-refresh-token revocation call (the closest equivalents --
  revoking all of a user's sign-in sessions, or removing the app's
  consent grant via Microsoft Graph as an admin -- both do much more
  than "disconnect this one integration" and require permissions this
  app has no reason to request). Disconnecting here means deleting our
  own stored copy of the tokens; the user can additionally remove this
  app's access from https://myaccount.microsoft.com/ if they want
  Microsoft's own record of the grant gone too. This is stated to the
  user at disconnect time (see the frontend copy), not left implicit.
"""
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.business import Business
from app.models.microsoft_integration import MicrosoftIntegration

logger = logging.getLogger(__name__)

_TENANT = "common"
MICROSOFT_AUTH_ENDPOINT = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_ENDPOINT = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"
MICROSOFT_GRAPH_ME_ENDPOINT = "https://graph.microsoft.com/v1.0/me"

# Read-only is deliberate, same reasoning as Google's scopes -- this
# integration only ever imports transactions out of a workbook, never
# writes back to it.
MICROSOFT_OAUTH_SCOPES = [
    "offline_access",  # required to receive a refresh_token
    "Files.Read",
    "User.Read",
]

_OAUTH_STATE_PURPOSE = "microsoft_oauth_state"
_OAUTH_STATE_EXPIRE_MINUTES = 10


class MicrosoftIntegrationError(AppError):
    """
    Raised for any Microsoft-OAuth/Graph-API failure that should surface
    to the caller as a clean error rather than an unhandled exception --
    mirrors GoogleIntegrationError exactly (see app.services.google_oauth).
    """

    status_code = 502
    code = "microsoft_integration_error"


def _require_configured() -> None:
    if not (
        settings.MICROSOFT_CLIENT_ID
        and settings.MICROSOFT_CLIENT_SECRET
        and settings.MICROSOFT_REDIRECT_URI
    ):
        raise MicrosoftIntegrationError(
            "Microsoft Excel integration isn't configured on this server yet. "
            "An administrator needs to set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, "
            "and MICROSOFT_REDIRECT_URI."
        )
    if not settings.MICROSOFT_TOKEN_ENCRYPTION_KEY:
        raise MicrosoftIntegrationError(
            "Microsoft Excel integration isn't configured on this server yet. "
            "An administrator needs to set MICROSOFT_TOKEN_ENCRYPTION_KEY."
        )


def _get_fernet() -> Fernet:
    try:
        return Fernet(settings.MICROSOFT_TOKEN_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise MicrosoftIntegrationError(
            "Microsoft Excel integration is misconfigured (invalid MICROSOFT_TOKEN_ENCRYPTION_KEY)."
        ) from exc


def encrypt_token(raw_token: str) -> str:
    return _get_fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise MicrosoftIntegrationError(
            "Stored Microsoft credentials could not be decrypted -- the integration needs to be "
            "reconnected."
        ) from exc


def create_oauth_state(business_id: str) -> str:
    """Short-lived, single-purpose signed token carrying which business initiated /connect."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES)
    payload = {"purpose": _OAUTH_STATE_PURPOSE, "business_id": business_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_oauth_state(state: str) -> str:
    """Returns the business_id encoded in a state token, or raises MicrosoftIntegrationError."""
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise MicrosoftIntegrationError(
            "This Microsoft sign-in link has expired or is invalid. Please try connecting again."
        ) from exc
    if payload.get("purpose") != _OAUTH_STATE_PURPOSE or "business_id" not in payload:
        raise MicrosoftIntegrationError("This Microsoft sign-in link is invalid. Please try connecting again.")
    return payload["business_id"]


def get_authorization_url(business_id: str) -> str:
    """Builds the Microsoft consent-screen URL the frontend redirects the browser to."""
    _require_configured()
    state = create_oauth_state(business_id)
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "response_mode": "query",
        "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
        "prompt": "consent",  # forces a fresh refresh_token on every connect, even for a returning user
        "state": state,
    }
    query = urlencode(params)
    return f"{MICROSOFT_AUTH_ENDPOINT}?{query}"


def _post_token_request(data: dict) -> dict:
    try:
        response = httpx.post(MICROSOFT_TOKEN_ENDPOINT, data=data, timeout=10.0)
    except httpx.HTTPError as exc:
        logger.warning("Network error contacting Microsoft's token endpoint: %s", exc)
        raise MicrosoftIntegrationError("Could not reach Microsoft. Please try again in a moment.") from exc

    if response.status_code != 200:
        logger.warning("Microsoft token endpoint returned %s: %s", response.status_code, response.text)
        raise MicrosoftIntegrationError(
            "Microsoft rejected this request. The connection may have expired -- please try connecting again."
        )
    return response.json()


def exchange_code_for_tokens(code: str) -> dict:
    """One-time auth code -> access_token + refresh_token + expires_in."""
    _require_configured()
    return _post_token_request(
        {
            "code": code,
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
        }
    )


def refresh_access_token(refresh_token: str) -> dict:
    """Exchanges a stored refresh_token for a new access_token + expires_in."""
    _require_configured()
    return _post_token_request(
        {
            "refresh_token": refresh_token,
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "scope": " ".join(MICROSOFT_OAUTH_SCOPES),
        }
    )


def get_user_email(access_token: str) -> str:
    try:
        response = httpx.get(
            MICROSOFT_GRAPH_ME_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise MicrosoftIntegrationError("Could not reach Microsoft to confirm the connected account.") from exc
    if response.status_code != 200:
        logger.warning("Microsoft Graph /me endpoint returned %s: %s", response.status_code, response.text)
        raise MicrosoftIntegrationError("Could not confirm which Microsoft account was connected.")
    data = response.json()
    # Work/school accounts often have `mail` set to null with the real
    # address only in `userPrincipalName`; personal accounts are the
    # reverse. Falling back covers both without needing to know which
    # kind of account is connecting.
    email = data.get("mail") or data.get("userPrincipalName")
    if not email:
        raise MicrosoftIntegrationError("Microsoft did not return an account email for this connection.")
    return email


def save_integration(db: Session, business: Business, tokens: dict, email: str) -> MicrosoftIntegration:
    """
    Upserts the one-per-business MicrosoftIntegration row. Mirrors
    google_oauth.save_integration exactly -- see that function's
    docstring for why a missing refresh_token in a response falls back
    to keeping the previous one rather than overwriting with nothing.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
    existing = (
        db.query(MicrosoftIntegration).filter(MicrosoftIntegration.business_id == business.id).first()
    )

    encrypted_access = encrypt_token(tokens["access_token"])
    encrypted_refresh = (
        encrypt_token(tokens["refresh_token"])
        if tokens.get("refresh_token")
        else (existing.encrypted_refresh_token if existing else None)
    )
    if not encrypted_refresh:
        logger.warning(
            "Microsoft did not return a refresh_token for business %s (tokens keys: %s)",
            business.id, list(tokens.keys()),
        )
        raise MicrosoftIntegrationError(
            "Microsoft didn't grant offline access on this connection. Please try connecting again."
        )

    if existing:
        existing.microsoft_email = email
        existing.encrypted_access_token = encrypted_access
        existing.encrypted_refresh_token = encrypted_refresh
        existing.access_token_expires_at = expires_at
        existing.scopes = tokens.get("scope", " ".join(MICROSOFT_OAUTH_SCOPES))
        existing.status = "connected"
        existing.last_sync_error = None
        integration = existing
    else:
        integration = MicrosoftIntegration(
            business_id=business.id,
            microsoft_email=email,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            access_token_expires_at=expires_at,
            scopes=tokens.get("scope", " ".join(MICROSOFT_OAUTH_SCOPES)),
            status="connected",
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)
    return integration


# Refresh a little early, not exactly at expiry, same reasoning as
# google_oauth._REFRESH_SKEW.
_REFRESH_SKEW = timedelta(minutes=2)


def get_valid_access_token(db: Session, integration: MicrosoftIntegration) -> str:
    """
    Returns a usable access token, refreshing it first if it's expired
    (or about to be). Mirrors google_oauth.get_valid_access_token exactly.
    """
    now = datetime.now(timezone.utc)
    expires_at = integration.access_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now < expires_at - _REFRESH_SKEW:
        return decrypt_token(integration.encrypted_access_token)

    refresh_token = decrypt_token(integration.encrypted_refresh_token)
    try:
        tokens = refresh_access_token(refresh_token)
    except MicrosoftIntegrationError:
        integration.status = "error"
        integration.last_sync_error = "Microsoft access could not be refreshed -- please reconnect."
        db.commit()
        raise

    integration.encrypted_access_token = encrypt_token(tokens["access_token"])
    integration.access_token_expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
    integration.status = "connected"
    db.commit()
    db.refresh(integration)
    return tokens["access_token"]


def disconnect(db: Session, integration: MicrosoftIntegration) -> None:
    """
    Deletes the stored integration row -- see this module's docstring
    for why there's no revoke-with-Microsoft call here, unlike Google's
    revoke_and_delete.
    """
    db.delete(integration)
    db.commit()
