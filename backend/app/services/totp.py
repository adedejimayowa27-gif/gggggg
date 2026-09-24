"""
Two-factor login (TOTP) -- Step 12, Batch 12.6.

Mirrors app/services/google_oauth.py's encrypt-before-storing pattern
for the secret (its own Fernet key, settings.TOTP_ENCRYPTION_KEY -- see
that setting's comment in app/core/config.py for why it's separate from
Google's/Microsoft's), and app/core/security.py's password hashing for
recovery codes (they're bearer credentials just like a password, so
they get the same bcrypt treatment, never stored or logged in plain
text).

Nothing here touches the database directly -- callers (the /auth/2fa/*
routes in app/api/routes/auth.py) own reading/writing the User row.
"""
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import hash_password, verify_password

ISSUER_NAME = "BizIntel"
RECOVERY_CODE_COUNT = 8


class TwoFactorError(AppError):
    status_code = 503
    code = "two_factor_misconfigured"


def _require_configured() -> None:
    if not settings.TOTP_ENCRYPTION_KEY:
        raise TwoFactorError(
            "Two-factor authentication isn't configured on this server yet. "
            "An administrator needs to set TOTP_ENCRYPTION_KEY."
        )


def _get_fernet() -> Fernet:
    try:
        return Fernet(settings.TOTP_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise TwoFactorError(
            "Two-factor authentication is misconfigured (invalid TOTP_ENCRYPTION_KEY)."
        ) from exc


def generate_secret() -> str:
    """A fresh base32 TOTP secret -- pass straight to encrypt_secret() before storing."""
    _require_configured()
    return pyotp.random_base32()


def encrypt_secret(raw_secret: str) -> str:
    _require_configured()
    return _get_fernet().encrypt(raw_secret.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    _require_configured()
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        # Either TOTP_ENCRYPTION_KEY changed since this row was written,
        # or the ciphertext is corrupted. Either way this account's 2FA
        # is now unverifiable from our side -- surfacing this as a clear
        # config error (rather than a confusing "invalid code" to the
        # user) is what should prompt an admin to investigate, rather
        # than a user locking themselves out trying codes that could
        # never have worked.
        raise TwoFactorError(
            "This account's two-factor setup can't be read (the server's encryption key may have "
            "changed). Please contact support."
        ) from exc


def provisioning_uri(secret: str, email: str) -> str:
    """The otpauth:// URI an authenticator app scans -- also usable as
    the QR code's payload (see qr_code_svg below) or typed in manually."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)


def qr_code_svg(otpauth_url: str) -> str:
    """
    Renders the QR code as an SVG string, entirely server-side -- no
    third-party QR-image service is called (which would mean handing a
    live TOTP secret to someone else's server as a URL parameter), and
    no new frontend dependency is needed (an <img> tag can render an SVG
    data URI directly).
    """
    img = qrcode.make(otpauth_url, image_factory=qrcode.image.svg.SvgPathImage)
    return img.to_string().decode()


def verify_totp_code(secret: str, code: str) -> bool:
    """valid_window=1 tolerates the code from one 30s step before/after
    now, for ordinary clock drift between the server and the person's
    phone -- without it, a technically-correct code typed a second too
    slowly would be rejected."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """
    Plaintext codes to show the user exactly once (at enable time or on
    regeneration) -- the caller must hash each with hash_recovery_code()
    before storing; nothing in this module ever persists the plaintext.
    """
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    """Recovery codes are bearer credentials like a password -- same
    bcrypt hashing, not a lighter-weight scheme."""
    return hash_password(code.strip().lower())


def consume_recovery_code(hashed_codes: list[str] | None, submitted_code: str) -> list[str] | None:
    """
    Checks `submitted_code` against every hash in `hashed_codes`. Returns
    the updated list (with the matching hash removed) if it matched, or
    None if it didn't -- the caller distinguishes those the same way as
    everywhere else (falsy vs a real error) and persists the returned
    list back onto the user row. Removing the matching hash outright
    (rather than flagging it "used") is what makes a code genuinely
    one-time -- there's no state to reset that would let it work twice.
    """
    if not hashed_codes:
        return None
    normalized = submitted_code.strip().lower()
    for hashed in hashed_codes:
        if verify_password(normalized, hashed):
            return [h for h in hashed_codes if h != hashed]
    return None
