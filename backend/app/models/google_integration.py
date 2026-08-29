"""
GoogleIntegration model (Step 9 -- Google Sheets integration).

Stores exactly one connected Google account per business, plus
synchronization metadata. Tokens are stored encrypted (see
app.services.google_oauth's encrypt_token/decrypt_token, using a Fernet
key from settings.GOOGLE_TOKEN_ENCRYPTION_KEY) -- this table is the only
place raw Google credentials ever touch storage, and even here they're
ciphertext, never plaintext. Nothing in any API response schema
(app.schemas.google_integration) ever includes the token columns --
that's what "never expose Google credentials to the frontend" (req #2)
actually means at the code level: the columns exist, but no route ever
serializes them.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class GoogleIntegration(Base):
    __tablename__ = "google_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # One Google connection per business -- unique, not just indexed.
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Connected account's email, for display only ("Connected as
    # owner@gmail.com") -- never used for authorization, only shown to
    # the business owner so they know which account is linked.
    google_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Encrypted (Fernet ciphertext, stored as text) -- never plaintext,
    # never returned by any schema.
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Space-separated OAuth scopes actually granted, so a future feature
    # needing a broader scope can tell whether reconnecting is required.
    scopes: Mapped[str] = mapped_column(String(500), nullable=False)

    # connected | error -- "error" is set by the sync/token-refresh logic
    # (Batch 9.4) when Google rejects a refresh (e.g. the user revoked
    # access from their Google account settings), so the UI can prompt a
    # reconnect instead of silently failing on every future sync attempt.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connected")

    # Which spreadsheet/worksheet this business has chosen to import
    # from (Batch 9.2/9.3 populate these once selection exists) --
    # nullable because right after connecting, nothing has been chosen
    # yet.
    spreadsheet_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spreadsheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    worksheet_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Synchronization metadata (requirement #10 -- track last successful
    # sync, and design for future background syncing). last_synced_at is
    # only updated on a *successful* sync; last_sync_error records the
    # most recent failure message without blocking retries.
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
        return f"<GoogleIntegration business_id={self.business_id} email={self.google_email!r} status={self.status}>"
