"""
Operating-expense routes (Step 13, Batch 2).

Nested under a business like transactions. Reading is open to every role;
adding and correcting an expense is day-to-day work ("member"); deleting one
changes net profit for every report, so it needs "admin". All writes are
audit-logged.

Route order matters: the fixed paths (/summary, /categories) are declared
before anything that takes an {expense_id}.
"""
import uuid
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    ensure_branch_belongs_to_business,
    get_current_user,
    get_owned_business,
    get_owned_expense,
    require_business_role,
)
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models.business import Business
from app.models.expense import Expense
from app.models.user import User
from app.schemas.expense import (
    ExpenseCategoryTotal,
    ExpenseCreate,
    ExpenseOut,
    ExpenseSummary,
    ExpenseUpdate,
    PaginatedExpenses,
)
from app.services.audit import client_ip, log_action
from app.services.expenses import category_choices, expense_filters, expense_total, expenses_by_category

router = APIRouter(prefix="/businesses/{business_id}/expenses", tags=["expenses"])

MAX_PAGE_SIZE = 200


def _check_range(start_date: date_type | None, end_date: date_type | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise ValidationError("start_date must not be after end_date.")


@router.get("", response_model=PaginatedExpenses)
def list_expenses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    category: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, min_length=1, max_length=200, description="Search category or description."),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    _check_range(start_date, end_date)
    filters = expense_filters(business.id, start_date, end_date, category, q, branch_id)

    total_amount, total = expense_total(db, *filters)
    items = (
        db.query(Expense)
        .filter(*filters)
        .order_by(Expense.date.desc(), Expense.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedExpenses(
        items=[ExpenseOut.model_validate(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
        total_amount=total_amount,
    )


@router.get("/summary", response_model=ExpenseSummary)
def get_expense_summary(
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    category: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    branch_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Total, count and per-category breakdown for the same filters as the list."""
    _check_range(start_date, end_date)
    filters = expense_filters(business.id, start_date, end_date, category, q, branch_id)
    total, count = expense_total(db, *filters)
    by_category = [
        ExpenseCategoryTotal(
            category=row["category"],
            total=row["total"],
            count=row["count"],
            share_percent=(row["total"] / total * 100).quantize(Decimal("0.1")) if total > 0 else Decimal(0),
        )
        for row in expenses_by_category(db, *filters)
    ]
    return ExpenseSummary(total=total, count=count, by_category=by_category)


@router.get("/categories", response_model=list[str])
def list_expense_categories(
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Categories this business already uses, then suggested ones it hasn't."""
    return category_choices(db, business.id)


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    ensure_branch_belongs_to_business(db, business, payload.branch_id)
    expense = Expense(id=uuid.uuid4(), business_id=business.id, **payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)

    log_action(
        db, "expense.created", business_id=business.id, actor_user_id=current_user.id,
        target_type="expense", target_id=str(expense.id),
        details={"category": expense.category, "amount": str(expense.amount), "date": expense.date.isoformat()},
        ip_address=client_ip(request),
    )
    return ExpenseOut.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("member")),
):
    expense = get_owned_expense(expense_id, business, db)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    if "branch_id" in changes:
        ensure_branch_belongs_to_business(db, business, changes["branch_id"])

    changed_fields = [f for f, value in changes.items() if getattr(expense, f) != value]
    if not changed_fields:
        return ExpenseOut.model_validate(expense)
    for field in changed_fields:
        setattr(expense, field, changes[field])
    db.commit()
    db.refresh(expense)

    log_action(
        db, "expense.updated", business_id=business.id, actor_user_id=current_user.id,
        target_type="expense", target_id=str(expense.id),
        details={"category": expense.category, "fields": sorted(changed_fields)},
        ip_address=client_ip(request),
    )
    return ExpenseOut.model_validate(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(require_business_role("admin")),
):
    expense = get_owned_expense(expense_id, business, db)
    details = {
        "category": expense.category,
        "amount": str(expense.amount),
        "date": expense.date.isoformat(),
    }
    db.delete(expense)
    db.commit()

    log_action(
        db, "expense.deleted", business_id=business.id, actor_user_id=current_user.id,
        target_type="expense", target_id=str(expense_id), details=details, ip_address=client_ip(request),
    )
