"""
TransactionTombstone model (Step 13, Batch 1 -- manual transaction editing).

Remembers the fingerprint of an *imported* transaction (one that came from
a file upload or a Google Sheets / Excel sync) after that transaction has
been deleted or edited inside the app.

Why this exists: every importer skips a source row whose fingerprint
already exists (see app.services.transactions.existing_fingerprints). That
is what stops a 6-hourly sync from re-inserting the same rows. But it also
means that, without a tombstone, deleting an imported sale here would let
the very next sync quietly bring it back, and editing one would make the
sheet's original row look "new" (its fingerprint no longer matches the
edited row) and insert a duplicate next to the corrected one. A tombstone
says "this source row was dealt with by a person -- do not import it again".

Only imported rows ever get a tombstone. Deleting a manually entered sale
leaves nothing behind, so the same sale can still be imported later.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class TransactionTombstone(Base):
    __tablename__ = "transaction_tombstones"
    __table_args__ = (
        UniqueConstraint("business_id", "fingerprint", name="uq_transaction_tombstones_business_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TransactionTombstone business_id={self.business_id} fingerprint={self.fingerprint[:8]}…>"
