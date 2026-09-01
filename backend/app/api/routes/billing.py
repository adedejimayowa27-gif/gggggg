"""
Billing routes (Step 10, Batch 10.3).

GET /plans and GET .../subscription work with zero Stripe configuration
(every business is on the free plan by default). The checkout and
webhook routes need real Stripe keys and raise a clean 503 until then --
see app.services.billing.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.plan import Plan
from app.models.user import User
from app.schemas.billing import CheckoutSessionIn, CheckoutSessionOut, PlanOut, SubscriptionOut
from app.services.audit import client_ip, log_action
from app.services.billing import create_checkout_session, get_subscription, handle_webhook_event

router = APIRouter(tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    plans = db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.price_ngn.asc()).all()
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/businesses/{business_id}/subscription", response_model=SubscriptionOut)
def get_business_subscription(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    subscription = get_subscription(db, business)
    return SubscriptionOut.model_validate(subscription)


@router.post("/businesses/{business_id}/billing/checkout", response_model=CheckoutSessionOut)
def start_checkout(
    payload: CheckoutSessionIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_owned_business),
):
    plan = db.query(Plan).filter(Plan.key == payload.plan_key, Plan.is_active.is_(True)).first()
    if not plan:
        raise NotFoundError(f"No active plan with key {payload.plan_key!r}.")
    url = create_checkout_session(db, business, plan, payload.success_url, payload.cancel_url)
    log_action(
        db, "billing.checkout_started", business_id=business.id, actor_user_id=current_user.id,
        details={"plan_key": plan.key}, ip_address=client_ip(request),
    )
    return CheckoutSessionOut(checkout_url=url)


@router.post("/billing/webhook", status_code=200)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    handle_webhook_event(db, payload, signature)
    return {"received": True}
