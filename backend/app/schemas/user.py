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
