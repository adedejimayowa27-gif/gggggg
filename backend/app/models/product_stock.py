"""
ProductStock model (Step 13, Batch 3 -- inventory and stock).

Tracks how much of a product a business has on hand, and the level at
which it should be reordered. Products in this app are plain text (a
Transaction's `product` column, not a first-class row with its own id --
see app.api.routes.analytics's product ranking, which groups by that same
text), so a stock record is likewise keyed by product name, not a
product_id.

A NULL branch_id means one shared stock list for the whole business.
Setting branch_id tracks that product separately for one location. The
app enforces (rather than a DB constraint -- see the migration's
docstring for why) that a business has at most one stock record per
product name (case-insensitively) per branch, so "Rice" and "rice" don't
silently split into two records.

`quantity_on_hand` only ever changes through a StockAdjustment (restock,
damage/loss, correction, or an automatic sale deduction) so there is
always an audit trail explaining a change -- see app.services.stock.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class ProductStock(Base):
    __tablename__ = "product_stock"
    __table_args__ = (Index("ix_product_stock_business_id_product", "business_id", "product"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    product: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    # 0 means "not tracking a reorder point for this product" -- the alert
    # detector and the "low stock" filter both skip a record with
    # reorder_level == 0, since every quantity is trivially "at or above"
    # a zero threshold.
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ProductStock id={self.id} business_id={self.business_id} {self.product!r} qty={self.quantity_on_hand}>"
