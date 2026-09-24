"""
Transaction routes.

Nested under a specific business, same pattern as imports.py -- every
route depends on get_owned_business, so there is no path to another
business's transactions even if a user guesses an ID.
"""
import csv
import io
import uuid
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery, Session

from app.api.deps import get_current_user, get_owned_business, get_owned_transaction, require_business_role
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models.branch import Branch
from app.models.business import Business
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import PaginatedTransactions, TransactionCreate, TransactionOut, TransactionUpdate
from app.services.audit import client_ip, log_action
from app.services.billing import check_max_transactions_this_month
from app.services.import_pipeline import compute_fingerprint
from app.services.transactions import remember_imported_fingerprint

router = APIRouter(prefix="/businesses/{business_id}/transactions", tags=["transactions"])

MAX_PAGE_SIZE = 200
MAX_EXPORT_ROWS = 50_000


def _apply_filters(query: SAQuery, q: str | None, branch_id: uuid.UUID | None) -> SAQuery:
    """
    Shared by list_transactions and export_transactions so "export what
    I'm currently looking at" is guaranteed to mean the same thing as
    what's on screen -- both routes filter identically because they
    call this one function rather than keeping two copies of the same
    OR/ilike block in sync by hand.
    """
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Transaction.product.ilike(pattern),
                Transaction.category.ilike(pattern),
                Transaction.customer.ilike(pattern),
                Transaction.payment_method.ilike(pattern),
            )
        )
    if branch_id is not None:
        query = query.filter(Transaction.branch_id == branch_id)
    return query


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


@router.get("/export")
def export_transactions(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    Downloads every transaction matching the same q/branch_id filters as
    list_transactions, as a CSV -- not paginated, since the entire point
    of an export is "give me everything that matches", not one page at
    a time. Capped at MAX_EXPORT_ROWS as a defensive limit against a
    pathological one-off, not a real constraint for this product's
    businesses; a genuinely bigger export would need actual streaming
    query pagination rather than this cap.

    Branch is exported by name, not raw ID -- an ID means nothing to
    someone opening this in Excel, so branches for this business are
    resolved to a name lookup once, up front, rather than once per row.
    """
    query = _apply_filters(
        db.query(Transaction).filter(Transaction.business_id == business.id), q, branch_id
    )
    transactions = (
        query.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(MAX_EXPORT_ROWS).all()
    )

    branch_names = {
        b.id: b.name for b in db.query(Branch).filter(Branch.business_id == business.id)
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Date", "Product", "Quantity", "Selling Price", "Cost Price", "Category", "Customer", "Payment Method", "Branch"]
    )
    for t in transactions:
        writer.writerow(
            [
                t.date.isoformat(),
                t.product,
                t.quantity,
                t.selling_price,
                t.cost_price if t.cost_price is not None else "",
                t.category or "",
                t.customer or "",
                t.payment_method or "",
                branch_names.get(t.branch_id, "") if t.branch_id else "",
            ]
        )
    buffer.seek(0)

    safe_business_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in business.name).strip() or "business"
    filename = f"{safe_business_name.replace(' ', '-')}-transactions.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    base_query = _apply_filters(
        db.query(Transaction).filter(Transaction.business_id == business.id), q, branch_id
    )

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


# --- Manual entry, editing and deleting (Step 13, Batch 1) -------------------
#
# Roles: adding and correcting a sale is day-to-day work ("member"); deleting
# one removes it from every report, so it needs "admin". Both are audit-logged.

# The fields that identify a sale for duplicate detection (see
# import_pipeline.compute_fingerprint). Changing any of them changes the
# transaction's fingerprint.
_FINGERPRINT_FIELDS = ("date", "product", "quantity", "selling_price", "cost_price")


def _ensure_branch_belongs_to_business(db: Session, business: Business, branch_id: uuid.UUID | None) -> None:
    if branch_id is None:
        return
    exists = (
        db.query(Branch.id).filter(Branch.id == branch_id, Branch.business_id == business.id).first()
    )
    if not exists:
        raise ValidationError("That branch does not belong to this business.", code="invalid_branch")


def _canonical(value: Decimal | None) -> Decimal | None:
    """Drop trailing zeros (2.500 -> 2.5, 10.00 -> 10) so the fingerprint
    reads the way a spreadsheet cell would, whether the number was typed
    here or read back from the database's fixed-precision column."""
    if value is None:
        return None
    return Decimal(format(value.normalize(), "f"))


def _fingerprint_for(transaction: Transaction) -> str:
    row = {field: getattr(transaction, field) for field in _FINGERPRINT_FIELDS}
    for field in ("quantity", "selling_price", "cost_price"):
        row[field] = _canonical(row[field])
    return compute_fingerprint(str(transaction.business_id), row)


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    """
    Records one sale by hand. Counts toward the plan's monthly transaction
    limit exactly like an imported row. Two genuinely separate sales of the
    same product, quantity and price on the same day are both allowed --
    unlike an import, a person typing a sale in means it.
    """
    check_max_transactions_this_month(db, business)
    _ensure_branch_belongs_to_business(db, business, payload.branch_id)

    transaction = Transaction(
        id=uuid.uuid4(),
        business_id=business.id,
        import_session_id=None,
        **payload.model_dump(),
    )
    transaction.fingerprint = _fingerprint_for(transaction)
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    log_action(
        db, "transaction.created", business_id=business.id, actor_user_id=current_user.id,
        target_type="transaction", target_id=str(transaction.id),
        details={"product": transaction.product, "date": transaction.date.isoformat()},
        ip_address=client_ip(request),
    )
    return TransactionOut.model_validate(transaction)


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    """
    Changes only the fields that were sent. Works on imported rows too. If
    the edit changes what identifies the sale (date, product, quantity or
    price), the original source row is remembered so the next sync or
    re-upload does not insert it again next to the corrected one.
    """
    transaction = get_owned_transaction(transaction_id, business, db)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}

    if "branch_id" in changes:
        _ensure_branch_belongs_to_business(db, business, changes["branch_id"])

    changed_fields = [f for f, value in changes.items() if getattr(transaction, f) != value]
    if not changed_fields:
        return TransactionOut.model_validate(transaction)

    for field in changed_fields:
        setattr(transaction, field, changes[field])

    if any(f in _FINGERPRINT_FIELDS for f in changed_fields):
        remember_imported_fingerprint(db, transaction)  # tombstones the OLD fingerprint
        transaction.fingerprint = _fingerprint_for(transaction)

    db.commit()
    db.refresh(transaction)

    log_action(
        db, "transaction.updated", business_id=business.id, actor_user_id=current_user.id,
        target_type="transaction", target_id=str(transaction.id),
        details={"product": transaction.product, "fields": sorted(changed_fields)},
        ip_address=client_ip(request),
    )
    return TransactionOut.model_validate(transaction)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    """
    Permanently removes one transaction. If it came from an import or sync,
    its source row is remembered so it is not brought back by the next
    sync. Any alert that pointed at it is kept (its link is just cleared).
    """
    transaction = get_owned_transaction(transaction_id, business, db)
    details = {
        "product": transaction.product,
        "date": transaction.date.isoformat(),
        "quantity": str(transaction.quantity),
        "selling_price": str(transaction.selling_price),
        "was_imported": transaction.import_session_id is not None,
    }
    remember_imported_fingerprint(db, transaction)
    db.delete(transaction)
    db.commit()

    log_action(
        db, "transaction.deleted", business_id=business.id, actor_user_id=current_user.id,
        target_type="transaction", target_id=str(transaction_id),
        details=details, ip_address=client_ip(request),
    )
