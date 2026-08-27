"""
AI assistant tool functions.

Plain Python functions the LLM will later be restricted to calling as
"tools" -- every number they return comes from the same kind of SQL
aggregation used in app/api/routes/analytics.py (SUM/COUNT in the DB,
never pulled into Python and summed in a loop, and never estimated by
the model itself). No AI/LLM code lives in this module; it is purely
the ground-truth data layer the assistant will be wired up to in a
later step.

Every function takes `db` and `business` (the same `Business` instance
returned by `app.api.deps.get_owned_business`) plus already-resolved
`date` bounds, and scopes its query to that business -- these functions
never take a business_id or a raw user id, so there is no way for a
caller to accidentally query another business's data.

Return values are plain JSON-safe dicts (floats and ISO date strings,
not Decimal/date objects), since these are meant to be handed back to
an LLM as tool-call results.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.business import Business
from app.models.transaction import Transaction
from app.services.analytics import DateRangePreset, resolve_date_range

_VALID_PRODUCT_METRICS = {
    "units_sold",
    "revenue",
    "total_cost",
    "gross_profit",
    "transaction_count",
}


# ---------------------------------------------------------------------------
# Small internal helpers
# ---------------------------------------------------------------------------


def _validate_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValidationError("start_date must not be after end_date.")


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 50:
        raise ValidationError("limit must be between 1 and 50.")


def _validate_metric(metric: str) -> None:
    if metric not in _VALID_PRODUCT_METRICS:
        raise ValidationError(
            f"Unsupported metric: {metric!r}. Must be one of {sorted(_VALID_PRODUCT_METRICS)}."
        )


def _period_filters(business: Business, start_date: date, end_date: date):
    return (
        Transaction.business_id == business.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    )


def _to_float(value, ndigits: int = 2) -> float:
    return round(float(value), ndigits)


# ---------------------------------------------------------------------------
# Ground-truth data functions
# ---------------------------------------------------------------------------


def get_revenue(db: Session, business: Business, start_date: date, end_date: date) -> dict:
    """Total revenue (quantity * selling_price) for the business in [start_date, end_date].

    Always includes `transaction_count` and `has_data` alongside the number
    itself -- a bare `"revenue": 0.0` is ambiguous (a genuinely flat period
    vs. no transactions imported for that range at all), and the model is
    told in the system prompt to check `has_data` and say so explicitly
    rather than guess which case it's looking at.
    """
    _validate_range(start_date, end_date)

    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    count_expr = func.count(Transaction.id)
    row = (
        db.query(revenue_expr.label("revenue"), count_expr.label("transaction_count"))
        .filter(*_period_filters(business, start_date, end_date))
        .one()
    )

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "revenue": _to_float(row.revenue),
        "transaction_count": row.transaction_count,
        "has_data": row.transaction_count > 0,
    }
    if row.transaction_count == 0:
        result["note"] = "No transactions found for this business in this date range."
    return result


def get_profit(db: Session, business: Business, start_date: date, end_date: date) -> dict:
    """Revenue, total cost, gross profit and profit margin for [start_date, end_date].

    Includes `transaction_count`/`has_data`/`note` for the same
    insufficient-data reason as `get_revenue` -- see that function's
    docstring.
    """
    _validate_range(start_date, end_date)

    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    count_expr = func.count(Transaction.id)

    row = (
        db.query(
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            count_expr.label("transaction_count"),
        )
        .filter(*_period_filters(business, start_date, end_date))
        .one()
    )

    revenue = Decimal(row.revenue)
    total_cost = Decimal(row.total_cost)
    gross_profit = revenue - total_cost
    profit_margin = (gross_profit / revenue * 100) if revenue > 0 else Decimal(0)

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "revenue": _to_float(revenue),
        "total_cost": _to_float(total_cost),
        "gross_profit": _to_float(gross_profit),
        "profit_margin": _to_float(profit_margin),
        "transaction_count": row.transaction_count,
        "has_data": row.transaction_count > 0,
    }
    if row.transaction_count == 0:
        result["note"] = "No transactions found for this business in this date range."
    return result


def get_expenses(db: Session, business: Business, start_date: date, end_date: date) -> dict:
    """Total cost of goods sold (quantity * cost_price) for [start_date, end_date].

    Includes `transaction_count`/`has_data`/`note` for the same
    insufficient-data reason as `get_revenue` -- see that function's
    docstring.
    """
    _validate_range(start_date, end_date)

    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    count_expr = func.count(Transaction.id)
    row = (
        db.query(cost_expr.label("total_cost"), count_expr.label("transaction_count"))
        .filter(*_period_filters(business, start_date, end_date))
        .one()
    )

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_cost": _to_float(row.total_cost),
        "transaction_count": row.transaction_count,
        "has_data": row.transaction_count > 0,
    }
    if row.transaction_count == 0:
        result["note"] = "No transactions found for this business in this date range."
    return result


def get_product_sales(
    db: Session,
    business: Business,
    start_date: date,
    end_date: date,
    product: str,
) -> dict:
    """Units, revenue, cost and profit for a single named product (case-insensitive exact match)."""
    _validate_range(start_date, end_date)

    units_expr = func.coalesce(func.sum(Transaction.quantity), 0)
    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    count_expr = func.count(Transaction.id)

    row = (
        db.query(
            units_expr.label("units_sold"),
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            count_expr.label("transaction_count"),
        )
        .filter(
            *_period_filters(business, start_date, end_date),
            func.lower(Transaction.product) == product.strip().lower(),
        )
        .one()
    )

    revenue = Decimal(row.revenue)
    total_cost = Decimal(row.total_cost)

    result = {
        "product": product,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "units_sold": _to_float(row.units_sold, ndigits=3),
        "revenue": _to_float(revenue),
        "total_cost": _to_float(total_cost),
        "gross_profit": _to_float(revenue - total_cost),
        "transaction_count": row.transaction_count,
        "has_data": row.transaction_count > 0,
    }
    if row.transaction_count == 0:
        result["note"] = (
            f"No transactions found for product {product!r} in this date range. "
            "This may mean the product name doesn't match exactly, or it simply wasn't sold then."
        )
    return result


def _product_breakdown(db: Session, business: Business, start_date: date, end_date: date) -> list[dict]:
    """Per-product totals for [start_date, end_date], one SQL GROUP BY query. Internal helper."""
    units_expr = func.coalesce(func.sum(Transaction.quantity), 0)
    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    count_expr = func.count(Transaction.id)

    rows = (
        db.query(
            Transaction.product.label("product"),
            units_expr.label("units_sold"),
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            count_expr.label("transaction_count"),
        )
        .filter(*_period_filters(business, start_date, end_date))
        .group_by(Transaction.product)
        .all()
    )

    items = []
    for row in rows:
        revenue = Decimal(row.revenue)
        total_cost = Decimal(row.total_cost)
        items.append(
            {
                "product": row.product,
                "units_sold": _to_float(row.units_sold, ndigits=3),
                "revenue": _to_float(revenue),
                "total_cost": _to_float(total_cost),
                "gross_profit": _to_float(revenue - total_cost),
                "transaction_count": row.transaction_count,
            }
        )
    return items


def get_top_products(
    db: Session,
    business: Business,
    start_date: date,
    end_date: date,
    limit: int = 5,
    metric: str = "revenue",
) -> dict:
    """Top `limit` products by `metric` (units_sold/revenue/total_cost/gross_profit/transaction_count)."""
    _validate_range(start_date, end_date)
    _validate_limit(limit)
    _validate_metric(metric)

    items = _product_breakdown(db, business, start_date, end_date)
    ranked = sorted(items, key=lambda item: item[metric], reverse=True)[:limit]

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "metric": metric,
        "products": ranked,
        "has_data": len(ranked) > 0,
    }
    if not ranked:
        result["note"] = "No transactions found for this business in this date range."
    return result


def get_slow_products(
    db: Session,
    business: Business,
    start_date: date,
    end_date: date,
    limit: int = 5,
    metric: str = "units_sold",
) -> dict:
    """Bottom `limit` products by `metric` -- the slowest/least profitable movers."""
    _validate_range(start_date, end_date)
    _validate_limit(limit)
    _validate_metric(metric)

    items = _product_breakdown(db, business, start_date, end_date)
    ranked = sorted(items, key=lambda item: item[metric])[:limit]

    result = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "metric": metric,
        "products": ranked,
        "has_data": len(ranked) > 0,
    }
    if not ranked:
        result["note"] = "No transactions found for this business in this date range."
    return result


def compare_periods(
    db: Session,
    business: Business,
    period_a_start: date,
    period_a_end: date,
    period_b_start: date,
    period_b_end: date,
) -> dict:
    """
    Compare revenue/cost/profit between two periods (e.g. "this month" vs
    "last month"). period_a is the baseline; period_b is compared against it.
    """
    period_a = get_profit(db, business, period_a_start, period_a_end)
    period_b = get_profit(db, business, period_b_start, period_b_end)

    def _pct_change(old: float, new: float) -> float | None:
        if old == 0:
            return None
        return round((new - old) / abs(old) * 100, 2)

    return {
        "period_a": period_a,
        "period_b": period_b,
        "revenue_change_pct": _pct_change(period_a["revenue"], period_b["revenue"]),
        "gross_profit_change_pct": _pct_change(
            period_a["gross_profit"], period_b["gross_profit"]
        ),
    }


# ---------------------------------------------------------------------------
# Natural-language date-range resolution
# ---------------------------------------------------------------------------

_LAST_N_DAYS_RE = re.compile(r"^(?:last|past)\s+(\d+)\s+days?$")
_LAST_N_WEEKS_RE = re.compile(r"^(?:last|past)\s+(\d+)\s+weeks?$")
_LAST_N_MONTHS_RE = re.compile(r"^(?:last|past)\s+(\d+)\s+months?$")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    return start, next_month_start - timedelta(days=1)


def _shift_months(anchor: date, months_back: int) -> date:
    """Return the first-of-month date `months_back` months before anchor's month."""
    total_months = anchor.year * 12 + (anchor.month - 1) - months_back
    year, month = divmod(total_months, 12)
    return date(year, month + 1, 1)


def resolve_natural_date_range(phrase: str, today: date | None = None) -> tuple[date, date]:
    """
    Turn a natural-language date phrase into a concrete inclusive
    (start_date, end_date) pair, extending `resolve_date_range` (which only
    understands the fixed today/7d/30d/90d/custom presets) with the looser
    phrasing an LLM is likely to pass along from a user's question.

    Supported phrases (case-insensitive): "today", "yesterday",
    "this week", "last week", "this month", "last month", "this year",
    "last year", "last N days", "last N weeks", "last N months" (and
    "past" as a synonym for "last").

    Raises ValidationError if the phrase isn't recognized -- callers should
    surface that back to the LLM/user rather than guessing a range.
    """
    reference_today = today or date.today()
    normalized = phrase.strip().lower()

    if normalized == "today":
        return resolve_date_range(DateRangePreset.TODAY, today=reference_today)

    if normalized == "yesterday":
        yesterday = reference_today - timedelta(days=1)
        return yesterday, yesterday

    if normalized == "this week":
        start = reference_today - timedelta(days=reference_today.weekday())
        return start, reference_today

    if normalized == "last week":
        start_of_this_week = reference_today - timedelta(days=reference_today.weekday())
        end_of_last_week = start_of_this_week - timedelta(days=1)
        start_of_last_week = end_of_last_week - timedelta(days=6)
        return start_of_last_week, end_of_last_week

    if normalized == "this month":
        return reference_today.replace(day=1), reference_today

    if normalized == "last month":
        first_of_this_month = reference_today.replace(day=1)
        last_day_of_prev_month = first_of_this_month - timedelta(days=1)
        return _month_bounds(last_day_of_prev_month.year, last_day_of_prev_month.month)

    if normalized == "this year":
        return reference_today.replace(month=1, day=1), reference_today

    if normalized == "last year":
        return date(reference_today.year - 1, 1, 1), date(reference_today.year - 1, 12, 31)

    match = _LAST_N_DAYS_RE.match(normalized)
    if match:
        n = int(match.group(1))
        if n < 1:
            raise ValidationError("Number of days must be at least 1.")
        return reference_today - timedelta(days=n - 1), reference_today

    match = _LAST_N_WEEKS_RE.match(normalized)
    if match:
        n = int(match.group(1))
        if n < 1:
            raise ValidationError("Number of weeks must be at least 1.")
        return reference_today - timedelta(weeks=n) + timedelta(days=1), reference_today

    match = _LAST_N_MONTHS_RE.match(normalized)
    if match:
        n = int(match.group(1))
        if n < 1:
            raise ValidationError("Number of months must be at least 1.")
        start = _shift_months(reference_today, n)
        return start, reference_today

    raise ValidationError(f"Could not resolve date range phrase: {phrase!r}")
