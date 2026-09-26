"""
StockAdjustment model (Step 13, Batch 3 -- inventory and stock).

One row per change to a ProductStock's quantity_on_hand: the audit trail
that lets an owner see WHY their stock is what it is, not just what it
currently is. Every adjustment records `delta` (signed: positive adds
stock, negative removes it) and the `resulting_quantity` immediately
after it, so history reads as a plain ledger without needing to replay
every prior row to make sense of one entry.

`reason` is a plain string, not a DB enum (same reasoning as
Alert.alert_type) -- app.services.stock is the single place that creates
these and validates which reasons exist:
  - "initial"        the opening quantity when a stock record is created
  - "restock"        more arrived (delivery, production, ...)
  - "damage"         stock lost (spoilage, theft, breakage, ...)
  - "correction"     a manual count that overrides the recorded quantity
  - "sale"           automatic deduction for a sale (Business.
                     auto_deduct_stock_on_sale) -- related_transaction_id
                     is set
  - "sale_reversal"  automatic compensation when a sale-linked
                     transaction that already deducted stock is edited
                     or deleted -- related_transaction_id is set

`created_by_user_id` is null for a system-generated row ("sale" /
"sale_reversal", and any adjustment made from a background import/sync
with no acting user) and set for a person's own action ("restock" /
"damage" / "correction" / "initial", plus a "sale" caused by someone
typing a manual sale in directly).
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # A database-generated, strictly-increasing sequence -- NOT the same
    # as created_at. Two adjustments made within the same request (e.g.
    # reverse_linked_sale_adjustment's compensating row immediately
    # followed by a fresh deduction, both in one edit) land in the same
    # database transaction, and Postgres's now() returns that
    # transaction's START time for every statement in it -- so both rows
    # can get an IDENTICAL created_at. `seq` is what
    # reverse_linked_sale_adjustment actually orders by to find "the most
    # recent" row reliably; created_at is for display only.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False, index=True)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_stock_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_stock.id", ondelete="CASCADE"), nullable=False, index=True
    )

    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    resulting_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<StockAdjustment id={self.id} product_stock_id={self.product_stock_id} {self.reason} {self.delta:+}>"
