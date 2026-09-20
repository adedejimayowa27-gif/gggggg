"""
Password hashing and JWT helpers.

Kept isolated from route/business logic so auth mechanics can evolve
(e.g. swapping bcrypt rounds, adding refresh tokens) without touching
API code.
"""
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
