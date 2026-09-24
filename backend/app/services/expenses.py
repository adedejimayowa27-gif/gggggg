"""
Operating-expense helpers (Step 13, Batch 2), shared by the expenses
routes, the analytics summary and the AI assistant's tools so "how much
did this business spend in this period" has exactly one definition.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.expense import Expense

# Suggested up front; a business can type any other category it likes.
DEFAULT_EXPENSE_CATEGORIES = [
    "Rent",
    "Salaries & wages",
    "Transport & fuel",
    "Electricity & power",
    "Internet & airtime",
    "Marketing",
    "Supplies",
    "Repairs & maintenance",
    "Taxes & fees",
    "Other",
]


def _escape_like(text: str) -> str:
    """Make %, _ and \\ in user input match literally inside ILIKE."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def expense_filters(
    business_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
) -> list:
    """The filter list every expense query in the app is built from."""
    filters = [Expense.business_id == business_id]
    if start_date is not None:
        filters.append(Expense.date >= start_date)
    if end_date is not None:
        filters.append(Expense.date <= end_date)
    if category:
        filters.append(func.lower(Expense.category) == category.strip().lower())
    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        filters.append(
            or_(Expense.category.ilike(pattern, escape="\\"), Expense.description.ilike(pattern, escape="\\"))
        )
    if branch_id is not None:
        filters.append(Expense.branch_id == branch_id)
    return filters


def expense_total(db: Session, *filters) -> tuple[Decimal, int]:
    """(sum of amount, number of expenses) for the given filters."""
    row = db.query(func.coalesce(func.sum(Expense.amount), 0), func.count(Expense.id)).filter(*filters).one()
    return Decimal(row[0]), int(row[1])


def expenses_by_category(db: Session, *filters) -> list[dict]:
    """
    Totals per category, largest first. Grouped case-insensitively so
    "rent" and "Rent" are one line, shown under whichever spelling sorts
    first.
    """
    key = func.lower(Expense.category)
    rows = (
        db.query(
            func.min(Expense.category).label("category"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(*filters)
        .group_by(key)
        .order_by(func.sum(Expense.amount).desc(), func.min(Expense.category))
        .all()
    )
    return [{"category": r.category, "total": Decimal(r.total), "count": int(r.count)} for r in rows]


def category_choices(db: Session, business_id: uuid.UUID) -> list[str]:
    """Categories this business already uses (most recent first), followed
    by any suggested defaults it hasn't used yet."""
    used_rows = (
        db.query(func.min(Expense.category), func.max(Expense.date))
        .filter(Expense.business_id == business_id)
        .group_by(func.lower(Expense.category))
        .order_by(func.max(Expense.date).desc())
        .all()
    )
    used = [row[0] for row in used_rows]
    seen = {c.lower() for c in used}
    return used + [c for c in DEFAULT_EXPENSE_CATEGORIES if c.lower() not in seen]
