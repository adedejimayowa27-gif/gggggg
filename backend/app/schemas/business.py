"""
Pydantic schemas for Business-related requests and responses.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=255)


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
