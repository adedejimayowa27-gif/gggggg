"""
Google OAuth service (Step 9 -- Google Sheets integration, Batch 9.1).

Everything Google-credential-related lives here: building the consent
URL, exchanging an auth code for tokens, refreshing an expired access
token, encrypting/decrypting tokens at rest, and reading/writing the
GoogleIntegration row. No route handler ever touches a raw token
directly -- they all go through get_valid_access_token(), which returns
a live, usable access token and handles refreshing transparently.

Security notes (requirements #1, #2, #8):
- Tokens are Fernet-encrypted before being written to the DB, and
  decrypted only in memory, only long enough to make one Google API call
  or one refresh request. They're never logged, never included in any
  Pydantic response schema (see app.schemas.google_integration), and
  never sent to the frontend in any form.
- The OAuth "state" parameter is a short-lived, signed JWT carrying the
  business_id -- not a bare, guessable business_id -- so the callback
  (which Google hits as an unauthenticated browser redirect, with no
  Authorization header) can trust which business initiated the flow
  without a separate server-side session store. It's signed with the
  same SECRET_KEY as login tokens but with a distinct claim shape (no
  "sub" claim, a "purpose" claim) so it can never be mistaken for or
  misused as a login access token.
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
from app.models.google_integration import GoogleIntegration

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

# Read-only is deliberate -- this integration only ever imports
# transactions out of a sheet, never writes back to it, so there's no
# reason to request write access to the user's Drive/Sheets.
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

_OAUTH_STATE_PURPOSE = "google_oauth_state"
_OAUTH_STATE_EXPIRE_MINUTES = 10


class GoogleIntegrationError(AppError):
    """
    Raised for any Google-OAuth/Sheets-API failure that should surface to
    the caller as a clean error rather than an unhandled exception --
    Google not configured, a rejected/expired code, a revoked refresh
    token, or a network failure talking to Google. Kept distinct from
    ValidationError (bad input from *our* user) since these are always
    about Google's side of the conversation.
    """

    status_code = 502
    code = "google_integration_error"


def _require_configured() -> None:
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.GOOGLE_REDIRECT_URI):
        raise GoogleIntegrationError(
            "Google Sheets integration isn't configured on this server yet. "
            "An administrator needs to set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
            "and GOOGLE_REDIRECT_URI."
        )
    if not settings.GOOGLE_TOKEN_ENCRYPTION_KEY:
        raise GoogleIntegrationError(
            "Google Sheets integration isn't configured on this server yet. "
            "An administrator needs to set GOOGLE_TOKEN_ENCRYPTION_KEY."
        )


def _get_fernet() -> Fernet:
    try:
        return Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        # A malformed key is a server misconfiguration, not a user error,
        # but still shouldn't come back as a raw 500 traceback.
        raise GoogleIntegrationError(
            "Google Sheets integration is misconfigured (invalid GOOGLE_TOKEN_ENCRYPTION_KEY)."
        ) from exc


def encrypt_token(raw_token: str) -> str:
    return _get_fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        # Either the encryption key changed since this row was written,
        # or the ciphertext is corrupted -- either way, this token can
        # never be recovered, so the caller must treat this as
        # disconnected, not retry.
        raise GoogleIntegrationError(
            "Stored Google credentials could not be decrypted -- the integration needs to be "
            "reconnected."
        ) from exc


def create_oauth_state(business_id: str) -> str:
    """Short-lived, single-purpose signed token carrying which business initiated /connect."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES)
    payload = {"purpose": _OAUTH_STATE_PURPOSE, "business_id": business_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_oauth_state(state: str) -> str:
    """Returns the business_id encoded in a state token, or raises GoogleIntegrationError."""
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise GoogleIntegrationError("This Google sign-in link has expired or is invalid. Please try connecting again.") from exc
    if payload.get("purpose") != _OAUTH_STATE_PURPOSE or "business_id" not in payload:
        raise GoogleIntegrationError("This Google sign-in link is invalid. Please try connecting again.")
    return payload["business_id"]


def get_authorization_url(business_id: str) -> str:
    """Builds the Google consent-screen URL the frontend redirects the browser to."""
    _require_configured()
    state = create_oauth_state(business_id)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_OAUTH_SCOPES),
        "access_type": "offline",  # required to receive a refresh_token
        "prompt": "consent",  # forces a refresh_token on every connect, even for a returning user
        "state": state,
    }
    query = urlencode(params)
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


def _post_token_request(data: dict) -> dict:
    try:
        response = httpx.post(GOOGLE_TOKEN_ENDPOINT, data=data, timeout=10.0)
    except httpx.HTTPError as exc:
        logger.warning("Network error contacting Google's token endpoint: %s", exc)
        raise GoogleIntegrationError("Could not reach Google. Please try again in a moment.") from exc

    if response.status_code != 200:
        logger.warning("Google token endpoint returned %s: %s", response.status_code, response.text)
        raise GoogleIntegrationError(
            "Google rejected this request. The connection may have expired -- please try connecting again."
        )
    return response.json()


def exchange_code_for_tokens(code: str) -> dict:
    """One-time auth code -> access_token + refresh_token + expires_in."""
    _require_configured()
    return _post_token_request(
        {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    )


def refresh_access_token(refresh_token: str) -> dict:
    """Exchanges a stored refresh_token for a new access_token + expires_in."""
    _require_configured()
    return _post_token_request(
        {
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        }
    )


def get_user_email(access_token: str) -> str:
    try:
        response = httpx.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise GoogleIntegrationError("Could not reach Google to confirm the connected account.") from exc
    if response.status_code != 200:
        raise GoogleIntegrationError("Could not confirm which Google account was connected.")
    email = response.json().get("email")
    if not email:
        raise GoogleIntegrationError("Google did not return an account email for this connection.")
    return email


def save_integration(db: Session, business: Business, tokens: dict, email: str) -> GoogleIntegration:
    """
    Upserts the one-per-business GoogleIntegration row. Google only
    returns a refresh_token on the very first consent for a given app+
    account pairing (or when prompt=consent forces re-consent, which
    get_authorization_url always sets) -- if a refresh_token is missing
    from `tokens` (e.g. an edge case Google response), the previous one
    is kept rather than overwritten with nothing.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
    existing = db.query(GoogleIntegration).filter(GoogleIntegration.business_id == business.id).first()

    encrypted_access = encrypt_token(tokens["access_token"])
    encrypted_refresh = (
        encrypt_token(tokens["refresh_token"])
        if tokens.get("refresh_token")
        else (existing.encrypted_refresh_token if existing else None)
    )
    if not encrypted_refresh:
        raise GoogleIntegrationError(
            "Google didn't grant offline access on this connection. Please try connecting again."
        )

    if existing:
        existing.google_email = email
        existing.encrypted_access_token = encrypted_access
        existing.encrypted_refresh_token = encrypted_refresh
        existing.access_token_expires_at = expires_at
        existing.scopes = tokens.get("scope", " ".join(GOOGLE_OAUTH_SCOPES))
        existing.status = "connected"
        existing.last_sync_error = None
        integration = existing
    else:
        integration = GoogleIntegration(
            business_id=business.id,
            google_email=email,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            access_token_expires_at=expires_at,
            scopes=tokens.get("scope", " ".join(GOOGLE_OAUTH_SCOPES)),
            status="connected",
        )
        db.add(integration)

    db.commit()
    db.refresh(integration)
    return integration


# Refresh a little early, not exactly at expiry, so a Sheets API call
# that starts just before expiry doesn't fail mid-request.
_REFRESH_SKEW = timedelta(minutes=2)


def get_valid_access_token(db: Session, integration: GoogleIntegration) -> str:
    """
    Returns a usable access token, refreshing it first if it's expired
    (or about to be). Persists the refreshed token immediately so the
    next call doesn't refresh again unnecessarily. If Google rejects the
    refresh (e.g. the user revoked access from their Google account),
    marks the integration "error" so the UI can prompt a reconnect,
    rather than failing silently on every subsequent sync attempt.
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
    except GoogleIntegrationError:
        integration.status = "error"
        integration.last_sync_error = "Google access could not be refreshed -- please reconnect."
        db.commit()
        raise

    integration.encrypted_access_token = encrypt_token(tokens["access_token"])
    integration.access_token_expires_at = now + timedelta(seconds=tokens.get("expires_in", 3600))
    integration.status = "connected"
    db.commit()
    db.refresh(integration)
    return tokens["access_token"]


def revoke_and_delete(db: Session, integration: GoogleIntegration) -> None:
    """
    Best-effort revoke with Google, then delete the row regardless of
    whether the revoke call succeeded -- the user's clear intent when
    disconnecting is "stop using my Google account", and a network
    hiccup talking to Google's revoke endpoint shouldn't block that.
    """
    try:
        access_token = decrypt_token(integration.encrypted_access_token)
        httpx.post(GOOGLE_REVOKE_ENDPOINT, params={"token": access_token}, timeout=10.0)
    except Exception:  # noqa: BLE001 -- disconnect must succeed locally regardless
        logger.warning("Could not revoke Google token for business %s (proceeding with local disconnect)", integration.business_id)

    db.delete(integration)
    db.commit()
