"""
Onboarding routes (Step 13, Batch 4): the getting-started checklist and
the sample-data load/remove actions.

Anyone on the business can read the checklist. Loading or removing
sample data inserts/deletes a lot of rows at once, so it needs "admin".
Both are audit-logged.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business, require_business_role
from app.db.session import get_db
from app.models.business import Business
from app.models.user import User
from app.schemas.onboarding import OnboardingStatus, SampleDataLoaded, SampleDataRemoved
from app.services.audit import client_ip, log_action
from app.services.sample_data import load_sample_data, onboarding_status, remove_sample_data

router = APIRouter(prefix="/businesses/{business_id}", tags=["onboarding"])


@router.get("/onboarding", response_model=OnboardingStatus)
def get_onboarding_status(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    return OnboardingStatus(**onboarding_status(db, business))


@router.post("/sample-data", response_model=SampleDataLoaded, status_code=status.HTTP_201_CREATED)
def load_sample(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    counts = load_sample_data(db, business, current_user.id)
    log_action(
        db, "sample_data.loaded", business_id=business.id, actor_user_id=current_user.id,
        target_type="business", target_id=str(business.id), details=counts, ip_address=client_ip(request),
    )
    return SampleDataLoaded(**counts)


@router.delete("/sample-data", response_model=SampleDataRemoved)
def remove_sample(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    counts = remove_sample_data(db, business)
    log_action(
        db, "sample_data.removed", business_id=business.id, actor_user_id=current_user.id,
        target_type="business", target_id=str(business.id), details=counts, ip_address=client_ip(request),
    )
    return SampleDataRemoved(**counts)
