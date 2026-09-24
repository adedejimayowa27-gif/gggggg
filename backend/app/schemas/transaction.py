"""
Pydantic schemas for Transaction requests and responses.
"""
import uuid
import datetime as dt
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

MIN_TRANSACTION_YEAR = 2000
# A sale entered "today" in Lagos can already be tomorrow's date in UTC, and
# vice versa, so a one-day grace avoids rejecting a perfectly normal entry
# purely because of the server's timezone.
FUTURE_DATE_GRACE_DAYS = 1


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    import_session_id: uuid.UUID | None
    date: dt.date
    product: str
    quantity: Decimal
    selling_price: Decimal
    cost_price: Decimal | None
    category: str | None
    customer: str | None
    payment_method: str | None
    branch_id: uuid.UUID | None
    created_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


def _blank_to_none(value):
    """Trim strings; an empty/whitespace-only string means "not provided"."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# Numeric limits mirror the Transaction columns (Numeric(14, 3) for quantity,
# Numeric(14, 2) for money) so an oversized value is a clean 422 here rather
# than a database error further down.
Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
OptionalText255 = Annotated[Annotated[str, Field(max_length=255)] | None, BeforeValidator(_blank_to_none)]
OptionalText100 = Annotated[Annotated[str, Field(max_length=100)] | None, BeforeValidator(_blank_to_none)]


def _check_date(value: dt.date) -> dt.date:
    if value.year < MIN_TRANSACTION_YEAR:
        raise ValueError(f"Date must be in {MIN_TRANSACTION_YEAR} or later.")
    if value > dt.date.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS):
        raise ValueError("Date cannot be in the future.")
    return value


def _check_product(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Product is required.")
    return value


class TransactionCreate(BaseModel):
    """One sale entered by hand (the same fields an import maps)."""

    date: dt.date
    product: str = Field(max_length=255)
    quantity: Quantity
    selling_price: Money
    cost_price: Money | None = None
    category: OptionalText255 = None
    customer: OptionalText255 = None
    payment_method: OptionalText100 = None
    branch_id: uuid.UUID | None = None

    _validate_date = field_validator("date")(_check_date)
    _validate_product = field_validator("product")(_check_product)


class TransactionUpdate(BaseModel):
    """
    Partial update (PATCH). Only fields that were actually sent are
    changed. The optional fields (cost price, category, customer, payment
    method, branch) can be cleared by sending them as null; the four
    required ones (date, product, quantity, selling price) cannot.
    """

    date: dt.date | None = None
    product: str | None = Field(default=None, max_length=255)
    quantity: Quantity | None = None
    selling_price: Money | None = None
    cost_price: Money | None = None
    category: OptionalText255 = None
    customer: OptionalText255 = None
    payment_method: OptionalText100 = None
    branch_id: uuid.UUID | None = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: dt.date | None) -> dt.date | None:
        return None if value is None else _check_date(value)

    @field_validator("product")
    @classmethod
    def _validate_product(cls, value: str | None) -> str | None:
        return None if value is None else _check_product(value)

    @model_validator(mode="after")
    def _required_fields_cannot_be_cleared(self):
        for field in ("date", "product", "quantity", "selling_price"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be cleared.")
        return self
