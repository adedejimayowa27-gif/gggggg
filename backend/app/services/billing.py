"""
Billing service (Step 10, Batch 10.3, requirement #1).

Two independent halves:

1. Usage limits -- check_usage_limit() and the specific *_would_exceed()
   helpers. Pure DB queries against a business's current Plan; work
   whether or not Stripe is configured, since the free plan doesn't need
   a payment processor at all.

2. Stripe integration -- create_checkout_session(), handle_webhook_event().
   Gracefully raise BillingNotConfiguredError until real Stripe keys
   exist (settings.STRIPE_SECRET_KEY etc.), same pattern as
   app.services.google_oauth's _require_configured(). Cannot be tested
   against real Stripe from this environment (no network access to
   Stripe's API here) -- tested with mocked stripe.* calls instead; a
   real Stripe account and one live test are needed after deploying.
"""
import logging
import uuid

import stripe
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ValidationError
from app.models.branch import Branch
from app.models.business import Business
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.models.user import User

logger = logging.getLogger(__name__)


class BillingNotConfiguredError(AppError):
    status_code = 503
    code = "billing_not_configured"


def _require_stripe_configured() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise BillingNotConfiguredError(
            "Billing isn't configured on this server yet. An administrator needs to set "
            "STRIPE_SECRET_KEY."
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def get_free_plan(db: Session) -> Plan:
    plan = db.query(Plan).filter(Plan.key == "free").first()
    if not plan:
        raise AppError("The free plan is not configured. Run the billing migration.", code="no_free_plan")
    return plan


def create_free_subscription(db: Session, business: Business) -> Subscription:
    """Called once, when a business is created -- mirrors
    app.services.team.create_owner_membership's role for team rows."""
    plan = get_free_plan(db)
    subscription = Subscription(business_id=business.id, plan_id=plan.id, status="active")
    db.add(subscription)
    return subscription


def get_subscription(db: Session, business: Business) -> Subscription:
    subscription = db.query(Subscription).filter(Subscription.business_id == business.id).first()
    if not subscription:
        # Every business should have one (auto-created + backfilled) --
        # this is a defensive fallback, not the expected path.
        subscription = create_free_subscription(db, business)
        db.commit()
        db.refresh(subscription)
    return subscription


# ---------------------------------------------------------------------------
# Usage limits
# ---------------------------------------------------------------------------


def check_max_businesses(db: Session, user: User) -> None:
    """
    Raises if creating one more business would exceed the limit of
    whichever of the user's *existing* businesses has the tightest plan
    limit (a brand-new user with no businesses yet has no plan to check
    against, so they're always allowed their first one).
    """
    from app.services.team import get_user_businesses  # local import avoids a circular import

    existing = get_user_businesses(db, user)
    if not existing:
        return
    tightest_limit = None
    for business in existing:
        subscription = get_subscription(db, business)
        limit = subscription.plan.max_businesses_per_user
        if limit is not None and (tightest_limit is None or limit < tightest_limit):
            tightest_limit = limit
    if tightest_limit is not None and len(existing) >= tightest_limit:
        raise ValidationError(
            f"Your current plan allows up to {tightest_limit} business(es). "
            "Upgrade your plan to create more."
        )


def check_max_branches(db: Session, business: Business) -> None:
    subscription = get_subscription(db, business)
    limit = subscription.plan.max_branches_per_business
    if limit is None:
        return
    current_count = db.query(Branch).filter(Branch.business_id == business.id).count()
    if current_count >= limit:
        raise ValidationError(
            f"This plan allows up to {limit} branch(es) per business. Upgrade to add more."
        )


def check_max_team_members(db: Session, business: Business) -> None:
    subscription = get_subscription(db, business)
    limit = subscription.plan.max_team_members_per_business
    if limit is None:
        return
    current_count = (
        db.query(TeamMember)
        .filter(TeamMember.business_id == business.id, TeamMember.status == "active")
        .count()
    )
    if current_count >= limit:
        raise ValidationError(
            f"This plan allows up to {limit} team member(s) per business. Upgrade to add more."
        )


def check_max_transactions_this_month(db: Session, business: Business) -> None:
    """
    Checked before persisting new transactions (a file import confirm,
    or a Sheets sync) -- counts transactions created so far in the
    current calendar month, not the total ever imported, so a monthly
    cap resets naturally every month.
    """
    subscription = get_subscription(db, business)
    limit = subscription.plan.max_transactions_per_month
    if limit is None:
        return
    from datetime import date

    month_start = date.today().replace(day=1)
    current_count = (
        db.query(Transaction)
        .filter(Transaction.business_id == business.id, Transaction.created_at >= month_start)
        .count()
    )
    if current_count >= limit:
        raise ValidationError(
            f"This plan allows up to {limit} transactions per month, and this business has "
            "already reached that limit this month. Upgrade to import more."
        )


# ---------------------------------------------------------------------------
# Stripe integration
# ---------------------------------------------------------------------------


def create_checkout_session(db: Session, business: Business, plan: Plan, success_url: str, cancel_url: str) -> str:
    """Returns the Stripe-hosted checkout page URL for upgrading a business to `plan`."""
    _require_stripe_configured()
    if not plan.stripe_price_id:
        raise BillingNotConfiguredError(f"Plan {plan.key!r} has no Stripe price configured yet.")

    subscription = get_subscription(db, business)
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(business.id),
            customer=subscription.stripe_customer_id,  # None is fine -- Stripe creates one
        )
    except stripe.error.StripeError as exc:
        logger.warning("Stripe checkout session creation failed: %s", exc)
        raise BillingNotConfiguredError("Could not start checkout. Please try again.") from exc
    return session.url


def handle_webhook_event(db: Session, payload: bytes, signature: str) -> None:
    """
    Verifies and applies a Stripe webhook event. Handles the 3 events
    that actually change a subscription's state; anything else is
    accepted and ignored (Stripe expects a 2xx for events it doesn't
    need acted on, not an error).
    """
    _require_stripe_configured()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise BillingNotConfiguredError("STRIPE_WEBHOOK_SECRET is not configured.")

    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise ValidationError("Invalid Stripe webhook signature.") from exc

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        business_id_str = data.get("client_reference_id")
        try:
            business_id = uuid.UUID(business_id_str) if business_id_str else None
        except ValueError:
            business_id = None
        subscription = (
            db.query(Subscription).filter(Subscription.business_id == business_id).first()
            if business_id
            else None
        )
        if subscription:
            subscription.stripe_customer_id = data.get("customer")
            subscription.stripe_subscription_id = data.get("subscription")
            subscription.status = "active"
            db.commit()

    elif event_type == "customer.subscription.updated":
        subscription = (
            db.query(Subscription).filter(Subscription.stripe_subscription_id == data["id"]).first()
        )
        if subscription:
            subscription.status = data.get("status", subscription.status)
            db.commit()

    elif event_type == "customer.subscription.deleted":
        subscription = (
            db.query(Subscription).filter(Subscription.stripe_subscription_id == data["id"]).first()
        )
        if subscription:
            free_plan = get_free_plan(db)
            subscription.plan_id = free_plan.id
            subscription.status = "active"
            subscription.stripe_subscription_id = None
            db.commit()
