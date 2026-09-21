"""
Transaction routes.

Nested under a specific business, same pattern as imports.py -- every
route depends on get_owned_business, so there is no path to another
business's transactions even if a user guesses an ID.
"""
import uuid
from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.db.session import get_db
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.transaction import PaginatedTransactions, TransactionOut

router = APIRouter(prefix="/businesses/{business_id}/transactions", tags=["transactions"])

MAX_PAGE_SIZE = 200


class LookupField(str, Enum):
    """
    Transaction fields whose distinct values are worth offering as
    autocomplete suggestions -- category and product for the Simulator's
    "applies to" selector, payment_method and customer for completeness
    since the same endpoint covers them for free.
    """

    CATEGORY = "category"
    PRODUCT = "product"
    PAYMENT_METHOD = "payment_method"
    CUSTOMER = "customer"


LOOKUP_COLUMNS = {
    LookupField.CATEGORY: Transaction.category,
    LookupField.PRODUCT: Transaction.product,
    LookupField.PAYMENT_METHOD: Transaction.payment_method,
    LookupField.CUSTOMER: Transaction.customer,
}


@router.get("/field-values", response_model=list[str])
def list_field_values(
    field: LookupField = Query(...),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Distinct, non-null values recorded for one transaction field, sorted
    alphabetically -- built for autocomplete/dropdown inputs (the
    Simulator's category/product selector) so picking a scope means
    choosing from the business's actual data instead of typing a name
    that has to match exactly, with a typo silently producing an
    empty/wrong-looking result and no indication why.

    Capped at 500 distinct values: comfortably past any real product
    catalog or category list for this product's businesses, without
    ever pulling in every historical value unbounded.
    """
    column = LOOKUP_COLUMNS[field]
    rows = (
        db.query(column)
        .filter(Transaction.business_id == business.id, column.isnot(None))
        .distinct()
        .order_by(column)
        .limit(500)
        .all()
    )
    return [row[0] for row in rows if row[0]]


@router.get("", response_model=PaginatedTransactions)
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    q is a plain substring search across the four text fields someone
    would actually be trying to find a sale by -- product, category,
    customer, payment method -- OR'd together rather than a dedicated
    search endpoint, so search results are just a filtered page of the
    same paginated list the page already renders (same shape, same
    sort), not a second, differently-structured response the frontend
    has to handle separately.
    """
    base_query = db.query(Transaction).filter(Transaction.business_id == business.id)

    if q:
        pattern = f"%{q}%"
        base_query = base_query.filter(
            or_(
                Transaction.product.ilike(pattern),
                Transaction.category.ilike(pattern),
                Transaction.customer.ilike(pattern),
                Transaction.payment_method.ilike(pattern),
            )
        )

    if branch_id is not None:
        base_query = base_query.filter(Transaction.branch_id == branch_id)

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
