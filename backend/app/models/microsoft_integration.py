"""
MicrosoftIntegration model (Step 11, Batch 11.9 -- Excel/OneDrive
integration).

Deliberately structured identically to app.models.google_integration --
same one-per-business shape, same encrypted-token-at-rest approach, same
never-exposed-to-any-schema rule. See that model's docstring for the
full reasoning; this one only calls out where Microsoft's shape differs
from Google's.

Differences from GoogleIntegration, and why:
- `spreadsheet_id`/`spreadsheet_name` are named `workbook_item_id`/
  `workbook_name` instead -- a OneDrive Excel file is a "workbook", not
  a Google "spreadsheet", and its identifier is a Microsoft Graph drive-
  item ID, not a Google Drive file ID. Different name, same role.
- `worksheet_id` is stored *in addition to* `worksheet_title` -- the
  Microsoft Graph API's worksheet-values endpoint addresses a worksheet
  by its own ID (not by title the way Google's Sheets API range
  notation does), so the ID needs to be kept, not just the display name.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class MicrosoftIntegration(Base):
    __tablename__ = "microsoft_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # One Microsoft connection per business -- unique, not just indexed.
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Connected account's email, for display only ("Connected as
    # owner@outlook.com") -- never used for authorization.
    microsoft_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Encrypted (Fernet ciphertext, stored as text) -- never plaintext,
    # never returned by any schema. See app.services.microsoft_oauth's
    # encrypt_token/decrypt_token, keyed by settings.MICROSOFT_TOKEN_ENCRYPTION_KEY.
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Space-separated OAuth scopes actually granted.
    scopes: Mapped[str] = mapped_column(String(500), nullable=False)

    # connected | error -- same meaning as GoogleIntegration.status: "error"
    # is set when Microsoft rejects a token refresh (e.g. revoked
    # consent), so the UI can prompt a reconnect.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connected")

    # Which OneDrive Excel workbook/worksheet this business has chosen
    # to import from -- nullable because right after connecting, nothing
    # has been chosen yet.
    workbook_item_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    workbook_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worksheet_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worksheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The column mapping the user confirmed once -- reused automatically
    # by every subsequent "Sync Now" and by the scheduled background
    # sync, without asking again. Null until reviewed and saved once.
    confirmed_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Synchronization metadata -- last_synced_at only updated on a
    # *successful* sync; last_sync_error records the most recent failure
    # message without blocking retries.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business")

    def __repr__(self) -> str:
        return (
            f"<MicrosoftIntegration business_id={self.business_id} "
            f"email={self.microsoft_email!r} status={self.status}>"
        )
