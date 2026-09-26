"""
Business routes.

Every route here requires authentication (via get_current_user) and every
query/write is scoped to the current user's own businesses. A user should
never be able to see or modify another user's data, even by guessing an
ID -- ownership is checked at the query level, not just at creation time.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business, require_business_role
from app.db.session import get_db
from app.models.business import Business
from app.models.user import User
from app.schemas.business import BusinessCreate, BusinessOut, BusinessUpdate
from app.services.team import create_owner_membership, get_user_businesses
from app.services.billing import check_max_businesses, create_free_subscription
from app.services.audit import client_ip, log_action

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(
    payload: BusinessCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_max_businesses(db, current_user)

    business = Business(
        name=payload.name,
        industry=payload.industry,
        owner_id=current_user.id,
    )
    db.add(business)
    db.flush()  # assigns business.id before the membership/subscription rows reference it
    create_owner_membership(db, business, current_user)
    create_free_subscription(db, business)
    db.commit()
    db.refresh(business)

    log_action(
        db, "business.created", business_id=business.id, actor_user_id=current_user.id,
        target_type="business", target_id=str(business.id),
        details={"name": business.name}, ip_address=client_ip(request),
    )

    return BusinessOut.model_validate(business)


@router.get("", response_model=list[BusinessOut])
def list_businesses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Every business this user can access -- their own, plus any they've
    been added to as a team member (Batch 10.2). Before this batch, a
    team member could open a business directly by ID but it would never
    show up in their own list -- that's fixed here.
    """
    businesses = get_user_businesses(db, current_user)
    return [BusinessOut.model_validate(b) for b in businesses]


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(
    business: Business = Depends(get_owned_business),
):
    return BusinessOut.model_validate(business)


@router.patch("/{business_id}", response_model=BusinessOut)
def update_business(
    payload: BusinessUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    """
    Changes only the fields sent. Currently covers the business's name,
    industry, and its stock-tracking setting (Step 13, Batch 3:
    auto_deduct_stock_on_sale -- whether creating/editing/deleting a
    transaction automatically adjusts a matching stock record).
    """
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    changed_fields = [f for f, value in changes.items() if getattr(business, f) != value]
    if changed_fields:
        for field in changed_fields:
            setattr(business, field, changes[field])
        db.commit()
        db.refresh(business)

        log_action(
            db, "business.updated", business_id=business.id, actor_user_id=current_user.id,
            target_type="business", target_id=str(business.id),
            details={"fields": sorted(changed_fields)}, ip_address=client_ip(request),
        )
    return BusinessOut.model_validate(business)
