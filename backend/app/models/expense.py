"""
Expense model (Step 13, Batch 2).

An operating expense: money the business spends that is NOT the cost of
the goods it sells -- rent, salaries, transport, electricity, airtime and
so on. (What the goods cost is `Transaction.cost_price`; that stays where
it is and still feeds gross profit.) Gross profit minus operating
expenses is the business's net profit, which is what the owner actually
keeps.

Like a Transaction, an expense belongs to one business and, optionally,
one branch. A NULL branch means shared overhead that isn't attributed to
any single branch (e.g. head-office rent).
"""
import uuid
from datetime import date as date_type, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_business_id_date", "business_id", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # Free text on purpose (with suggestions in the UI) so a business can
    # name its own categories; the breakdown groups them case-insensitively.
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Expense id={self.id} business_id={self.business_id} {self.category} {self.amount}>"
