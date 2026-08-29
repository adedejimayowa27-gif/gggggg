"""
ImportSession model.

Represents one upload attempt of a spreadsheet/CSV file. This is the
backbone of the reusable import pipeline: it stores the raw parsed rows
and detected columns right after upload (status="pending_mapping"), then
gets updated with the final column mapping and validation results once
the user confirms the import (status="completed" or "failed").

Keeping raw_rows on this record (rather than only in memory) means the
upload and confirm steps can be separate HTTP requests without needing
sticky sessions or re-uploading the file -- this is also what makes it
straightforward to later add other sources (Google Sheets, POS exports)
that produce the same raw_rows shape but skip the file-upload step.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class ImportSession(Base):
    __tablename__ = "import_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # "file" (a CSV/XLSX upload) | "google_sheets" (Batch 9.4's sync).
    # Existing rows get "file" via server_default -- this column's
    # addition changes nothing about the file-upload path's behavior.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="file")

    # "pending_mapping" -> uploaded and parsed, waiting for user to confirm
    #   column mapping.
    # "completed" -> user confirmed, valid rows stored as Transactions.
    # "failed" -> every row was invalid, or the file itself couldn't be
    #   processed at all.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_mapping")

    # Column headers detected in the uploaded file, in original order.
    detected_columns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # The parsed rows, keyed by the *original* column headers. Kept until
    # the import is confirmed so the confirm step doesn't need the file
    # re-uploaded. Example: [{"Item Name": "Widget", "Qty Sold": "3"}, ...]
    raw_rows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # The suggested mapping computed at upload time, e.g.
    # {"product": "Item Name", "quantity": "Qty Sold", ...}. The user can
    # override this before confirming; the mapping actually used is stored
    # separately below once confirmed.
    suggested_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # The mapping the user actually confirmed with (may differ from
    # suggested_mapping). Null until confirmed.
    confirmed_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    total_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # List of {"row_number": int, "errors": [str, ...]} for rows that
    # failed validation, so the user can see exactly what went wrong.
    row_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Only ever populated for source="google_sheets" -- how many parsed
    # rows were skipped because a Transaction with the same fingerprint
    # already exists for this business (requirement #7). Null/unused for
    # file uploads, which have no duplicate-detection step.
    skipped_duplicate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business", back_populates="import_sessions")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="import_session"
    )

    def __repr__(self) -> str:
        return f"<ImportSession id={self.id} filename={self.filename!r} status={self.status!r}>"
