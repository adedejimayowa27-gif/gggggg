"""
Pydantic schemas for User-related requests and responses.

Naming convention used throughout this project:
- <Thing>Create  -> request body for creating a resource
- <Thing>Out     -> response body (never includes secrets like passwords)
- <Thing>Update  -> request body for partial updates (added when needed)
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_email_verified: bool
    is_2fa_enabled: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    # Batch 12.3: an opaque, single-use-per-rotation session token -- see
    # app/models/refresh_token.py. Store it alongside access_token and
    # send it to POST /auth/refresh (to get a new access_token before
    # this one expires) or POST /auth/logout (to revoke this session).
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class TwoFactorChallenge(BaseModel):
    """
    Returned by POST /auth/login INSTEAD OF Token when the account has
    2FA enabled -- the password was correct, but no session exists yet.
    Redeem challenge_token plus a code at POST /auth/2fa/verify-login to
    get the real Token. See app/core/security.py's
    create_two_factor_challenge_token for what's actually inside it.
    """

    two_factor_required: bool = True
    challenge_token: str


class TwoFactorVerifyLoginRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=4, max_length=64)


class TwoFactorSetupOut(BaseModel):
    """
    A pending, unconfirmed enrollment -- POST /auth/2fa/enable with a
    real code from this secret is what actually turns 2FA on. Calling
    setup again before enabling replaces this (see the route's
    docstring), so a person can freely restart if they scan the wrong
    thing or lose the page.
    """

    secret: str
    otpauth_url: str
    qr_code_svg: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorEnableOut(BaseModel):
    # Shown exactly once -- not retrievable again after this response.
    # Losing them all AND the authenticator device means losing access
    # to the account (support/manual DB intervention territory) -- the
    # frontend should make this consequence clear before the person
    # navigates away.
    recovery_codes: list[str]


class TwoFactorCodeConfirmRequest(BaseModel):
    """
    Shared by disable and recovery-code regeneration -- both require
    proving both "I know the password" AND "I currently control the
    authenticator/a recovery code", not just an active session, since a
    session alone (e.g. an unattended unlocked browser tab) is exactly
    what 2FA exists to add a second check beyond.
    """

    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class DeleteAccountRequest(BaseModel):
    # Re-confirms identity for a destructive, irreversible action even
    # though the request already carries a valid access token -- same
    # reasoning most apps use before "delete my account": a token can
    # be sitting in an unlocked, unattended browser tab in a way a
    # password typically isn't.
    password: str = Field(min_length=1, max_length=128)
