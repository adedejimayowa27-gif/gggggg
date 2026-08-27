"""
Pydantic schemas for Transaction responses.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    import_session_id: uuid.UUID | None
    date: date
    product: str
    quantity: Decimal
    selling_price: Decimal
    cost_price: Decimal | None
    category: str | None
    customer: str | None
    payment_method: str | None
    created_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
