"""
Transaction model.

Represents one validated row of business transaction data (a sale, for
this step). Every transaction belongs to exactly one business and,
optionally, the import session it was created from -- import_session_id
is nullable so future steps (manual entry, POS sync) can create
transactions without an import session.
"""
import uuid
from datetime import date as date_type, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    import_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # Batch 6.1: optional fields completing the 8-field standard schema.
    # All three are nullable so existing/simple transaction files (which
    # only ever mapped the first 5 fields) continue to import and read
    # exactly as before -- nothing downstream should assume these are set.
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business", back_populates="transactions")
    import_session: Mapped["ImportSession | None"] = relationship(
        "ImportSession", back_populates="transactions"
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} product={self.product!r} date={self.date}>"
