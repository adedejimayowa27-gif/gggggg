"""
Transaction routes.

Nested under a specific business, same pattern as imports.py -- every
route depends on get_owned_business, so there is no path to another
business's transactions even if a user guesses an ID.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.db.session import get_db
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.transaction import PaginatedTransactions, TransactionOut

router = APIRouter(prefix="/businesses/{business_id}/transactions", tags=["transactions"])

MAX_PAGE_SIZE = 200


@router.get("", response_model=PaginatedTransactions)
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    base_query = db.query(Transaction).filter(Transaction.business_id == business.id)

    total = base_query.count()
    items = (
        base_query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedTransactions(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
