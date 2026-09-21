"""
TeamMember model (Step 10, Batch 10.2, requirement #4).

Every business's authorization now runs through this table, not just
Business.owner_id -- see app.api.deps.get_owned_business. Business.owner_id
is kept as-is (it remains the single source of truth for "who created
this business" and, later, who's billed for it -- Batch 10.3), but every
business also gets an "owner" TeamMember row automatically (created when
the business is created, and backfilled for pre-existing businesses in
this batch's migration), so permission-checking code has exactly one
path to follow instead of two.

Roles, most to least privileged: owner > admin > member > viewer.
- owner: full control, including removing other team members. A
  business's original owner_id user always has this role and can never
  be removed or demoted by anyone (enforced at the route layer).
- admin: everything a member can do, plus manage team membership, connect
  and configure integrations (Google Sheets, Excel/OneDrive), delete
  branches, read the audit log and start a plan upgrade.
- member: normal day-to-day work -- import data, run syncs, manage alerts,
  save and delete simulations, add and edit branches -- but can't manage
  the team or set up integrations.
- viewer: read-only. Sees everything the business shows, and can use tools
  that change nothing (the what-if preview, the AI assistant), but can't
  import, sync, change or delete anything.

Enforcement (Batch 12.4): every route under /businesses/{business_id}/...
declares its minimum role through app.api.deps -- get_owned_business for
read-only routes, require_business_role("member" | "admin" | "owner") for
everything else. The full table is in docs/API.md ("Roles and
permissions"), and tests/test_role_permissions.py fails if a route is added
without a declared role or a write route is left open to viewers.
(Before this batch only team management and a couple of destructive
actions checked roles; every other route accepted any active team member.)

status: "active" (can use the business now) or "pending" (invited by
email, but no account with that email exists yet -- see
app.services.team.link_pending_invites, called at signup, for how a
pending invite becomes active).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

ROLE_ORDER = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Nullable until a matching account exists -- see status/docstring.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Always set, even once user_id is filled in -- the identifier the
    # invite was actually made against, and what's shown in the team list
    # for a still-pending invite (which has no User row to join against).
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business")
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<TeamMember business_id={self.business_id} email={self.invited_email!r} role={self.role} status={self.status}>"
