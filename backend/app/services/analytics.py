"""
Analytics service.

Shared logic for turning a `range` query param (today/7d/30d/90d/custom)
into concrete (start_date, end_date) bounds. Every analytics endpoint
(summary, timeseries, products, breakdown) resolves its date range
through here so the "what does 7d mean" definition lives in exactly one
place.
"""
from datetime import date, timedelta
from enum import Enum

from app.core.exceptions import ValidationError


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
