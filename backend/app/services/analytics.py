"""
Analytics service.

Shared logic used by both app.api.routes.analytics and app.services.ai_tools
(the AI assistant's tool layer) so financial calculations, date-range
handling, and breakdown-dimension definitions live in exactly one place
rather than being re-derived independently by the HTTP layer and the AI
layer:

- Date-range resolution: turning a `range` query param
  (today/7d/30d/90d/custom) into concrete (start_date, end_date) bounds.
- The optional-breakdown vocabulary (BreakdownField, its unset-label
  placeholders).
- The core SQL aggregation building blocks (revenue_expr, cost_expr,
  units_expr, transaction_count_expr, period_filters) -- every endpoint
  and every AI tool that needs "this business's revenue/cost/units in a
  date range" builds its query from these same four expressions, so a
  future forecasting/alerts/Sheets-sync feature has one obvious place to
  import them from instead of re-writing the same SUM/COALESCE pattern a
  seventh or eighth time.
"""
from datetime import date, timedelta
from enum import Enum

from sqlalchemy import func

from app.core.exceptions import ValidationError
from app.models.business import Business
from app.models.transaction import Transaction


class DateRangePreset(str, Enum):
    TODAY = "today"
    LAST_7D = "7d"
    LAST_30D = "30d"
    LAST_90D = "90d"
    CUSTOM = "custom"


class Granularity(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class BreakdownField(str, Enum):
    """
    The optional transaction fields (Batch 6.1) a business may or may not
    actually populate. Kept as its own enum -- rather than a bare string
    query param -- so FastAPI validates it and so future consumers
    (forecasting, alerts) have one canonical list of "dimensions this
    business's data can be sliced by" to import instead of re-typing field
    names as strings.
    """

    CATEGORY = "category"
    CUSTOMER = "customer"
    PAYMENT_METHOD = "payment_method"


# Human-readable placeholder shown in a breakdown for transactions where
# the given optional field was never populated -- distinct per field so
# "Uncategorized" (a category concept) doesn't show up next to a payment
# method by mistake.
BREAKDOWN_UNSET_LABELS: dict[BreakdownField, str] = {
    BreakdownField.CATEGORY: "Uncategorized",
    BreakdownField.CUSTOMER: "Unspecified customer",
    BreakdownField.PAYMENT_METHOD: "Unspecified payment method",
}


def resolve_date_range(
    range_preset: DateRangePreset,
    start_date: date | None = None,
    end_date: date | None = None,
    today: date | None = None,
) -> tuple[date, date]:
    """
    Resolve a preset (+ optional explicit bounds) into an inclusive
    (start_date, end_date) pair.

    - today/7d/30d/90d: end_date is always "today" (or the injected
      `today`, used for testing); start_date is derived by subtracting
      the window length.
    - custom: both start_date and end_date must be provided by the
      caller and are used as-is (inclusive).
    """
    reference_today = today or date.today()

    if range_preset == DateRangePreset.CUSTOM:
        if start_date is None or end_date is None:
            raise ValidationError(
                "start_date and end_date are required when range=custom."
            )
        if start_date > end_date:
            raise ValidationError("start_date must not be after end_date.")
        return start_date, end_date

    window_days = {
        DateRangePreset.TODAY: 0,
        DateRangePreset.LAST_7D: 6,
        DateRangePreset.LAST_30D: 29,
        DateRangePreset.LAST_90D: 89,
    }[range_preset]

    resolved_start = reference_today - timedelta(days=window_days)
    return resolved_start, reference_today


# ---------------------------------------------------------------------------
# Shared SQL aggregation building blocks.
#
# Every one of these was previously written out inline, identically, in
# both app.api.routes.analytics (4 endpoints) and app.services.ai_tools
# (6 functions) -- the exact same func.coalesce(func.sum(...)) formulas,
# copy-pasted 10 times between the two files. Consolidating them here
# doesn't change any figure either module produces (the formulas are
# unchanged); it just gives future code (forecasting, alerts, a Sheets
# sync job) one place to get "this business's revenue/cost/units in a
# date range" from, instead of writing an 11th copy.
# ---------------------------------------------------------------------------


def revenue_expr():
    """SQL expression: SUM(quantity * selling_price), 0 if no rows."""
    return func.coalesce(func.sum(Transaction.quantity * Transaction.selling_price), 0)


def cost_expr():
    """SQL expression: SUM(quantity * cost_price), 0 if no rows."""
    return func.coalesce(func.sum(Transaction.quantity * Transaction.cost_price), 0)


def units_expr():
    """SQL expression: SUM(quantity), 0 if no rows."""
    return func.coalesce(func.sum(Transaction.quantity), 0)


def transaction_count_expr():
    """SQL expression: COUNT(*) over the filtered transactions."""
    return func.count(Transaction.id)


def period_filters(business: Business, start_date: date, end_date: date):
    """
    The (business_id, date >= start, date <= end) filter triple every
    query in this app scopes by. Returns a tuple so callers can splat it
    straight into `.filter(*period_filters(...))` alongside any extra
    filters of their own (e.g. a product-name match).
    """
    return (
        Transaction.business_id == business.id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    )
