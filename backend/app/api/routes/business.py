"""
Business routes.

Every route here requires authentication (via get_current_user) and every
query/write is scoped to the current user's own businesses. A user should
never be able to see or modify another user's data, even by guessing an
ID -- ownership is checked at the query level, not just at creation time.
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.user import User
from app.schemas.business import BusinessCreate, BusinessOut

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def create_business(
    payload: BusinessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = Business(
        name=payload.name,
        industry=payload.industry,
        owner_id=current_user.id,
    )
    db.add(business)
    db.commit()
    db.refresh(business)
    return BusinessOut.model_validate(business)


@router.get("", response_model=list[BusinessOut])
def list_businesses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    businesses = (
        db.query(Business)
        .filter(Business.owner_id == current_user.id)
        .order_by(Business.created_at.desc())
        .all()
    )
    return [BusinessOut.model_validate(b) for b in businesses]


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(
    business_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = (
        db.query(Business)
        .filter(Business.id == business_id, Business.owner_id == current_user.id)
        .first()
    )
    if not business:
        raise NotFoundError("Business not found.")
    return BusinessOut.model_validate(business)
