"""
Account-level self-service data operations (Step 12, Batch 12.5).

Two things live here, both scoped to "my own account, everything about
it" rather than any one business:

- export_account_data(): everything the account-holder is entitled to
  see about themselves, assembled into one JSON-serializable dict.
- delete_account(): permanently deletes the user row. Every other
  table this touches -- businesses they own, transactions, branches,
  import history, chat history, team memberships (both sides:
  memberships on their own businesses, and memberships they hold on
  someone else's), refresh tokens, integrations, subscriptions -- is
  wired with a real ON DELETE CASCADE (or SET NULL for audit_logs,
  deliberately -- see that model's docstring) at the database level,
  not just in the ORM, so a single `db.delete(user)` is genuinely
  enough to remove all of it. See the migrations under
  alembic/versions for each FK's ondelete clause if that ever needs
  re-verifying.

Both functions are read/act on `user` only -- callers (the /auth
routes) are responsible for authentication and, for deletion,
re-confirming the password before calling in.
"""
import logging

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.audit_log import AuditLog
from app.models.business import Business
from app.models.google_integration import GoogleIntegration
from app.models.microsoft_integration import MicrosoftIntegration
from app.models.subscription import Subscription
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.models.user import User
from app.services.audit import log_action
from app.services.billing import cancel_subscription

logger = logging.getLogger(__name__)


def businesses_blocking_deletion(db: Session, user: User) -> list[Business]:
    """
    Owned businesses that still have another *active* team member besides
    the owner -- deleting the account would cascade-delete the business
    itself (and every collaborator's access to it) with no warning to
    them, so these block self-deletion until the owner removes those
    members first. There's no way to "delete just the business" or
    transfer ownership yet (see app/models/audit_log.py's docstring), so
    removing members via DELETE /businesses/{id}/team/{member_id} is the
    only path to unblock this today.

    A business the user owns solo (no other active members -- the common
    case) is never blocked.
    """
    owned = db.query(Business).filter(Business.owner_id == user.id).all()
    if not owned:
        return []

    owned_ids = [b.id for b in owned]
    business_ids_with_other_members = {
        row[0]
        for row in db.query(TeamMember.business_id)
        .filter(
            TeamMember.business_id.in_(owned_ids),
            TeamMember.status == "active",
            TeamMember.user_id != user.id,
        )
        .distinct()
    }
    return [b for b in owned if b.id in business_ids_with_other_members]


def delete_account(db: Session, user: User) -> None:
    """
    Permanently deletes the account. Raises ConflictError (caught by the
    route, same as every other AppError) if the account owns a business
    other people still actively use -- see businesses_blocking_deletion.

    Ordering matters here:
    1. Check for blockers first -- before touching anything, so a
       blocked deletion changes nothing.
    2. Cancel any real Stripe subscriptions on owned businesses *before*
       deleting them -- once the business row (and its Subscription row)
       is gone, there is no longer anywhere in this app to look up the
       stripe_subscription_id to cancel it, and the person would keep
       being billed for a business that, from their side, no longer
       exists.
    3. Log the deletion *before* deleting the user row, not after
       (the reverse of the usual log-after-the-fact convention in
       app.services.audit) -- actor_user_id has to reference a row that
       still exists at insert time. The FK is ondelete="SET NULL", so
       this entry survives the deletion itself with actor_user_id
       nulled out; `details` keeps the email so the record still means
       something once that happens.
    4. Delete the user row. Every dependent row cascades at the database
       level (see this module's docstring).
    """
    blockers = businesses_blocking_deletion(db, user)
    if blockers:
        names = ", ".join(b.name for b in blockers)
        raise ConflictError(
            f"You still own {len(blockers)} business(es) with other active team members "
            f"({names}). Remove those members before deleting your account, or deleting it "
            "will remove their access with no warning.",
            code="account_owns_shared_businesses",
        )

    owned_business_ids = [b.id for b in db.query(Business.id).filter(Business.owner_id == user.id)]
    if owned_business_ids:
        subscriptions = (
            db.query(Subscription)
            .filter(Subscription.business_id.in_(owned_business_ids), Subscription.stripe_subscription_id.isnot(None))
            .all()
        )
        for subscription in subscriptions:
            cancel_subscription(subscription)

    log_action(
        db, "auth.account_deleted", actor_user_id=user.id,
        target_type="user", target_id=str(user.id),
        details={"email": user.email, "businesses_deleted": owned_business_ids and len(owned_business_ids) or 0},
    )

    db.delete(user)
    db.commit()


def export_account_data(db: Session, user: User) -> dict:
    """
    Everything about this account, in one JSON-serializable dict. Scoped
    deliberately: raw transaction rows are NOT included here (a business
    can hold tens of thousands of them -- see transactions.py's
    MAX_EXPORT_ROWS) -- each owned business instead gets a
    `transactions_export_url` pointing at its own existing CSV export
    endpoint, so a large business's data doesn't balloon this payload.
    Never includes hashed_password, refresh token values, or any
    integration's stored OAuth tokens (encrypted or not) -- see
    app/models/google_integration.py's docstring for why those never
    leave that table at all.
    """
    owned_businesses = db.query(Business).filter(Business.owner_id == user.id).all()
    owned_business_ids = [b.id for b in owned_businesses]

    subscriptions_by_business = {
        s.business_id: s
        for s in db.query(Subscription).filter(Subscription.business_id.in_(owned_business_ids))
    } if owned_business_ids else {}

    transaction_counts = dict(
        db.query(Transaction.business_id, sa_func.count(Transaction.id))
        .filter(Transaction.business_id.in_(owned_business_ids))
        .group_by(Transaction.business_id)
        .all()
    ) if owned_business_ids else {}

    google_by_business = {
        g.business_id: g
        for g in db.query(GoogleIntegration).filter(GoogleIntegration.business_id.in_(owned_business_ids))
    } if owned_business_ids else {}
    microsoft_by_business = {
        m.business_id: m
        for m in db.query(MicrosoftIntegration).filter(MicrosoftIntegration.business_id.in_(owned_business_ids))
    } if owned_business_ids else {}

    businesses_export = []
    for business in owned_businesses:
        subscription = subscriptions_by_business.get(business.id)
        google = google_by_business.get(business.id)
        microsoft = microsoft_by_business.get(business.id)
        members = (
            db.query(TeamMember)
            .filter(TeamMember.business_id == business.id, TeamMember.user_id != user.id)
            .all()
        )
        businesses_export.append(
            {
                "id": str(business.id),
                "name": business.name,
                "industry": business.industry,
                "created_at": business.created_at.isoformat(),
                "transaction_count": transaction_counts.get(business.id, 0),
                "transactions_export_url": f"/businesses/{business.id}/transactions/export",
                "subscription_plan_id": str(subscription.plan_id) if subscription else None,
                "subscription_status": subscription.status if subscription else None,
                "google_sheets_connected": bool(google),
                "google_sheets_email": google.google_email if google else None,
                "excel_onedrive_connected": bool(microsoft),
                "excel_onedrive_email": microsoft.microsoft_email if microsoft else None,
                "other_team_members": [
                    {"invited_email": m.invited_email, "role": m.role, "status": m.status}
                    for m in members
                ],
            }
        )

    memberships_elsewhere = (
        db.query(TeamMember)
        .join(Business, TeamMember.business_id == Business.id)
        .filter(TeamMember.user_id == user.id, Business.owner_id != user.id)
        .all()
    )

    # Capped, most recent first -- an account active for years could have
    # thousands of entries; this is a personal export, not a compliance
    # discovery dump, so recent history is what's actually useful here.
    recent_actions = (
        db.query(AuditLog)
        .filter(AuditLog.actor_user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(1000)
        .all()
    )

    return {
        "account": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_email_verified": user.is_email_verified,
            "is_2fa_enabled": user.is_2fa_enabled,
            "created_at": user.created_at.isoformat(),
        },
        "businesses_you_own": businesses_export,
        "team_memberships_on_other_businesses": [
            {
                "business_id": str(m.business_id),
                "business_name": m.business.name,
                "role": m.role,
                "status": m.status,
            }
            for m in memberships_elsewhere
        ],
        "recent_account_activity": [
            {
                "action": a.action,
                "business_id": str(a.business_id) if a.business_id else None,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent_actions
        ],
    }
