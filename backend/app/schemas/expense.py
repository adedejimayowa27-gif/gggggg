"""
Pydantic schemas for operating expenses (Step 13, Batch 2).
"""
import datetime as dt
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.transaction import OptionalText255, _check_date

# Numeric(14, 2) column; an expense is always money going out, so it must be
# more than zero (a zero or negative "expense" is a typo, not a real entry).
Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


def _check_category(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Category is required.")
    return value


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    date: dt.date
    category: str
    amount: Decimal
    description: str | None
    branch_id: uuid.UUID | None
    created_at: datetime


class PaginatedExpenses(BaseModel):
    items: list[ExpenseOut]
    total: int
    page: int
    page_size: int
    # Sum of `amount` across EVERY expense matching the filters -- not just
    # this page -- so the page can show "₦X spent" for the whole filtered set.
    total_amount: Decimal


class ExpenseCreate(BaseModel):
    date: dt.date
    category: str = Field(max_length=100)
    amount: Amount
    description: OptionalText255 = None
    branch_id: uuid.UUID | None = None

    _validate_date = field_validator("date")(_check_date)
    _validate_category = field_validator("category")(_check_category)


class ExpenseUpdate(BaseModel):
    """Partial update (PATCH): only fields that were sent change. Description
    and branch can be cleared with null; date, category and amount cannot."""

    date: dt.date | None = None
    category: str | None = Field(default=None, max_length=100)
    amount: Amount | None = None
    description: OptionalText255 = None
    branch_id: uuid.UUID | None = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: dt.date | None) -> dt.date | None:
        return None if value is None else _check_date(value)

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str | None) -> str | None:
        return None if value is None else _check_category(value)

    @model_validator(mode="after")
    def _required_fields_cannot_be_cleared(self):
        for field in ("date", "category", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be cleared.")
        return self


class ExpenseCategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int
    share_percent: Decimal  # of the filtered total, e.g. 42.5 means 42.5%


class ExpenseSummary(BaseModel):
    total: Decimal
    count: int
    by_category: list[ExpenseCategoryTotal]  # largest first
