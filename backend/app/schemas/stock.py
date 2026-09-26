"""
Pydantic schemas for inventory/stock (Step 13, Batch 3).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.schemas.transaction import OptionalText255

# Numeric(14, 3) columns, matching Transaction.quantity's precision.
NonNegativeQty = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
PositiveQty = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


def _check_product(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Product is required.")
    return value


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    branch_id: uuid.UUID | None
    product: str
    quantity_on_hand: Decimal
    reorder_level: Decimal
    updated_at: datetime


class StockOutWithFlag(StockOut):
    """StockOut plus whether this record is at or below its reorder
    level. Computed in app.services.stock.to_stock_out_with_flag rather
    than as a model property, so it's a real field in the JSON response
    (a bare @property isn't included in model_dump()/JSON output)."""

    is_low: bool


class PaginatedStock(BaseModel):
    items: list[StockOutWithFlag]
    total: int
    page: int
    page_size: int
    # Count of items LOW across the whole filtered set, not just this page.
    low_stock_count: int


class StockCreate(BaseModel):
    product: str = Field(max_length=255)
    branch_id: uuid.UUID | None = None
    quantity_on_hand: NonNegativeQty = Decimal(0)
    reorder_level: NonNegativeQty = Decimal(0)

    _validate_product = field_validator("product")(_check_product)


class StockUpdate(BaseModel):
    """Partial update (PATCH): only fields sent change. Quantity is
    deliberately not editable here -- it only ever changes through an
    adjustment, so there's always a record of why."""

    reorder_level: NonNegativeQty | None = None
    branch_id: uuid.UUID | None = None
    # Sentinel so "branch_id not sent" (leave alone) is distinguishable
    # from "branch_id: null" (move to shared/no branch) -- see
    # model_fields_set usage in the route.


class StockAdjustmentCreate(BaseModel):
    """
    `quantity`'s meaning depends on `reason`:
      - restock / damage: how much is being added or removed (> 0)
      - correction: the new absolute quantity on hand (>= 0)
    """

    reason: Literal["restock", "damage", "correction"]
    quantity: Decimal = Field(max_digits=14, decimal_places=3)
    note: OptionalText255 = None

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, value: Decimal, info) -> Decimal:
        reason = info.data.get("reason")
        if reason in ("restock", "damage") and value <= 0:
            raise ValueError("quantity must be more than zero for a restock or damage adjustment.")
        if reason == "correction" and value < 0:
            raise ValueError("quantity cannot be negative for a correction.")
        return value


class StockAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reason: str
    delta: Decimal
    resulting_quantity: Decimal
    note: str | None
    related_transaction_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class StockAdjustmentResult(BaseModel):
    stock: StockOutWithFlag
    adjustment: StockAdjustmentOut
