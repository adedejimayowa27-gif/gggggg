"""
Password hashing and JWT helpers.

Kept isolated from route/business logic so auth mechanics can evolve
(e.g. swapping bcrypt rounds, adding refresh tokens) without touching
API code.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Returns the subject (user id) if the token is valid, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def create_password_reset_token(user_id: str) -> str:
    """
    A short-lived JWT carrying a distinct "purpose" claim -- deliberately
    not reusing create_access_token, so a password-reset link can never
    double as a login token (or vice versa) even though both are signed
    with the same SECRET_KEY. Expiry is short (see
    settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES) since this token alone
    is enough to take over an account.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": user_id, "exp": expire, "purpose": "password_reset"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_password_reset_token(token: str) -> Optional[str]:
    """
    Returns the user id if the token is valid AND was specifically
    issued for password reset, else None. Checking the "purpose" claim
    is what stops a normal login access token from being replayed here
    to reset someone's password.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != "password_reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def generate_refresh_token() -> tuple[str, str]:
    """
    Returns (raw_token, token_hash). The raw token is returned to the
    client exactly once (in the login/signup/refresh response body) and
    never stored anywhere; only its SHA-256 hash is persisted
    (app.models.refresh_token.RefreshToken.token_hash), so a database
    leak alone can't be used to impersonate a session. secrets.token_urlsafe
    (not jwt.encode) on purpose: this token carries no claims of its own --
    it's just a high-entropy lookup key into that table, where expiry and
    revocation actually live.
    """
    raw_token = secrets.token_urlsafe(64)
    return raw_token, hash_refresh_token(raw_token)


def hash_refresh_token(raw_token: str) -> str:
    """The lookup key stored in refresh_tokens.token_hash. Deterministic
    (unlike bcrypt) on purpose -- a refresh/logout call needs to find the
    matching row with an indexed equality lookup, not by re-hashing and
    comparing against every stored hash."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_email_verification_token(user_id: str) -> str:
    """
    Same shape as create_password_reset_token above (a distinct
    "purpose" claim, signed with the same SECRET_KEY, so the two token
    kinds can never be swapped for each other), but with its own much
    longer expiry -- see EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES's
    comment in app/core/config.py for why.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": user_id, "exp": expire, "purpose": "email_verification"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_email_verification_token(token: str) -> Optional[str]:
    """Returns the user id if the token is valid AND was issued for email verification, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != "email_verification":
            return None
        return payload.get("sub")
    except JWTError:
        return None
