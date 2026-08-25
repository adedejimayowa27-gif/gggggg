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
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
