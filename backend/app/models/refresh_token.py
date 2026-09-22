"""
RefreshToken model (Step 12, Batch 12.3 -- real sessions).

Why a database row instead of just a second, longer-lived JWT: a JWT is
stateless by design, which is exactly why the *access* token uses one
(app/core/security.py's create_access_token -- no DB lookup needed on
every request). But that same statelessness means a JWT can't be revoked
before it expires. A refresh token has to be revocable -- on logout, and
on password reset (so a stolen password can't be used to keep a session
alive forever even after the legitimate owner resets it) -- so it's an
opaque random string, hashed at rest, checked against this table.

Rotation and reuse detection: every /auth/refresh call issues a new
refresh token and immediately revokes the old one (revoked_reason
"rotated"), linked by `family_id`. If a *revoked* token is ever presented
again, that's a strong signal it was copied (a legitimate client only
ever has the newest token in its family) -- app/api/routes/auth.py
responds by revoking every token in that family, forcing a real
re-login. `family_id` equals the first token's own id, so a family
needs no separate table.

Not covered by this batch (left for later, noted here rather than
silently skipped): a scheduled sweep of long-expired/revoked rows. They
cost nothing functionally -- refresh/logout only ever look up by
token_hash, which stays indexed -- but the table grows forever. Add a
delete-where-expired-or-revoked-before-N-days job alongside the existing
data-retention job (app/services/data_retention.py) when that starts to
matter.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 of the raw token, never the raw token itself -- same reason
    # passwords are hashed: a database leak alone shouldn't hand out
    # usable sessions. Unlike a password, this is already a 64-byte
    # high-entropy random value (see app.core.security.generate_refresh_token),
    # so a fast cryptographic hash is appropriate here; bcrypt's
    # deliberate slowness (right for low-entropy user passwords) would
    # just be wasted work on every refresh/logout lookup.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Shared by every token produced from the same login through
    # rotation, so "revoke this whole family" (reuse detected, or a
    # password reset revoking every session) is one query away.
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "rotated" (normal refresh), "logout", "password_reset", or
    # "reuse_detected" (see the module docstring). Free text, not an
    # enum -- purely descriptive, read by humans debugging a session
    # issue, never branched on in code.
    revoked_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.revoked_at is not None}>"
