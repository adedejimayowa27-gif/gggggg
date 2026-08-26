"""
Analytics service.

Shared logic for turning a `range` query param (today/7d/30d/90d/custom)
into concrete (start_date, end_date) bounds. Every analytics endpoint
(summary, timeseries, products) resolves its date range through here so
the "what does 7d mean" definition lives in exactly one place.
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
