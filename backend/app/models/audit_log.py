"""
AuditLog model (Step 10, Batch 10.4, requirement #5).

A plain, append-only record of who did what. business_id is nullable
because some actions are account-level, not business-level (login,
signup, before any business exists yet); actor_user_id is nullable for
the same reason in reverse (a system/background action with no human
behind it, e.g. a Stripe webhook updating a subscription).

Writing an audit log entry must never be able to break the action it's
recording -- see app.services.audit.log_action, which swallows and logs
any failure rather than raising.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base_class import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Dot-namespaced, e.g. "auth.login", "team_member.invited",
    # "branch.deleted", "billing.checkout_started" -- see
    # app.services.audit for the full list currently logged.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # What the action was done to, e.g. target_type="team_member",
    # target_id=<that row's id>. Both nullable -- not every action has a
    # single clear target (e.g. "auth.login" doesn't).
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Arbitrary extra context specific to this action (e.g. the invited
    # email + role for a "team_member.invited" entry). Never includes
    # secrets -- callers are responsible for only passing safe details.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} business_id={self.business_id} actor={self.actor_user_id}>"
