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
    # Step 13, Batch 3: whether creating/editing/deleting a transaction
    # automatically adjusts a matching stock record.
    auto_deduct_stock_on_sale: bool


class BusinessUpdate(BaseModel):
    """Partial update (PATCH): only fields sent change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=255)
    auto_deduct_stock_on_sale: bool | None = None
