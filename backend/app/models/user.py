"""
User model.

One user can own multiple businesses (see Business.owner_id). Auth
endpoints (Batch 3) will read/write through this model.

is_email_verified (Batch 12.2): tracked but not enforced. See
app/api/routes/auth.py's module docstring for the reasoning.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Batch 12.2: does NOT gate login or any route -- see
    # app/api/routes/auth.py's docstring for why. Purely informational
    # (the frontend shows a banner and a resend option until it's true).
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Batch 12.6: two-factor login (TOTP) ---
    # See alembic/versions/0022_two_factor_auth.py and
    # app/services/totp.py for the full design. totp_secret_encrypted
    # can be non-NULL while is_2fa_enabled is still false -- that's a
    # setup in progress (POST /auth/2fa/setup called, but
    # POST /auth/2fa/enable hasn't succeeded yet).
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_recovery_codes_hashed: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    businesses: Mapped[list["Business"]] = relationship(
        "Business", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
