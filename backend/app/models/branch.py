"""
Branch model (Step 10 -- SaaS production layer, requirement #3).

A business can optionally organize its operations into branches (e.g.
"Ikeja Store", "Lekki Warehouse"). Branches are purely additive and
opt-in: a business with zero branches behaves exactly as it always has
-- nothing elsewhere in the app requires a branch to exist, and
Transaction.branch_id (see app/models/transaction.py) is nullable, so
every transaction imported before this feature existed, and every one
imported by a business that never sets up branches, is completely
unaffected.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Exactly one branch per business may be marked default (enforced in
    # the route layer, not a DB constraint) -- used as a sensible
    # pre-selected choice in any future UI that lets a user assign a
    # transaction to a branch, never required.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business")

    def __repr__(self) -> str:
        return f"<Branch id={self.id} business_id={self.business_id} name={self.name!r}>"
