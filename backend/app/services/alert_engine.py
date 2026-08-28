"""
Alert detection engine (Step 8 -- Business Intelligence Alert Engine).

Pure detection: reads a business's real historical transactions
(read-only, same as scenario_engine.py) and produces a list of
AlertCandidate objects -- nothing is persisted here. Batch 8.4's
orchestrator runs every registered detector, deduplicates against
existing alerts, assigns final severity, and writes Alert rows.

Registry design (requirement #12): DETECTORS maps an alert_type string
to a detector function. This batch registers 3 detector functions
(unusual_sales, revenue_profit_change, falling_profit_margin); Batch 8.3
adds more entries to this same dict. Nothing about this module's shape
changes when a new detector is added.

Baseline design (requirement #2): where enough historical data exists,
detectors compare the current period against a business-specific
statistical baseline (mean/stddev of several past periods of the same
length) using a z-score, rather than a fixed percentage threshold --
what counts as "unusual" for a business that normally does ₦50,000/week
is different from one that normally does ₦5,000,000/week. When there
isn't enough history for that (requirement #11), a detector either falls
back to a simpler fixed-threshold comparison (documented per detector) or
skips entirely rather than guessing -- always stated in supporting_values
so it's never ambiguous which method produced an alert.
"""
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.models.business import Business
from app.services.analytics import cost_expr, period_filters, revenue_expr, transaction_count_expr, units_expr

# Minimum number of historical comparison windows required before a
# statistical baseline is trusted at all -- below this, a detector skips
# rather than compute a mean/stddev from too little evidence.
MIN_BASELINE_WINDOWS = 4

# z-score severity bands, shared by every statistically-driven detector.
_Z_SEVERITY_BANDS = [(3, "CRITICAL"), (2.5, "HIGH"), (2, "MEDIUM"), (1.5, "LOW")]

# Percentage-change severity bands, shared by every threshold-driven
# detector (period-over-period change, cost changes in Batch 8.3, etc.).
_PCT_SEVERITY_BANDS = [(50, "CRITICAL"), (30, "HIGH"), (15, "MEDIUM"), (8, "LOW")]


@dataclass(frozen=True)
class AlertCandidate:
    """One detector's finding, not yet persisted. Batch 8.4 turns these
    into Alert rows after deduplication."""

    alert_type: str
    severity: str
    title: str
    message: str
    period_start: date
    period_end: date
    supporting_values: dict
    dedupe_key: str
    affected_product: str | None = None
    affected_category: str | None = None
    affected_metric: str | None = None


def _severity_from_bands(magnitude: float, bands: list[tuple[float, str]]) -> str | None:
    """First band whose threshold `magnitude` clears, highest first. None
    if it doesn't clear even the lowest band -- meaning "not alert-worthy"."""
    for threshold, severity in bands:
        if magnitude >= threshold:
            return severity
    return None


def _period_totals(db: Session, business: Business, start: date, end: date) -> dict:
    """Revenue/cost/profit/margin/units/count for one window. Shared by
    every detector in this module -- same aggregation shape as
    app.services.analytics and app.services.ai_tools, reusing their exact
    SQL building blocks so a detector's numbers always agree with what
    the dashboard and the AI assistant would report for the same range.
    """
    row = (
        db.query(
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
            units_expr().label("units_sold"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, start, end))
        .one()
    )
    revenue = Decimal(row.revenue)
    total_cost = Decimal(row.total_cost)
    gross_profit = revenue - total_cost
    profit_margin = (gross_profit / revenue * 100) if revenue > 0 else Decimal(0)
    return {
        "revenue": revenue,
        "total_cost": total_cost,
        "gross_profit": gross_profit,
        "profit_margin": profit_margin,
        "units_sold": Decimal(row.units_sold),
        "transaction_count": row.transaction_count,
    }


def _consecutive_windows(end_date: date, window_days: int, count: int) -> list[tuple[date, date]]:
    """`count` consecutive, non-overlapping windows of `window_days` days,
    the most recent one ending on end_date, oldest first."""
    windows = []
    cursor_end = end_date
    for _ in range(count):
        cursor_start = cursor_end - timedelta(days=window_days - 1)
        windows.append((cursor_start, cursor_end))
        cursor_end = cursor_start - timedelta(days=1)
    windows.reverse()
    return windows


def _pct_change(old: Decimal, new: Decimal) -> Decimal | None:
    if old == 0:
        return None
    return (new - old) / abs(old) * 100


# ---------------------------------------------------------------------------
# Detector 1: unusually low/high sales (statistical baseline)
# ---------------------------------------------------------------------------


def detect_unusual_sales(db: Session, business: Business, today: date | None = None) -> list[AlertCandidate]:
    """
    Compares this week's revenue (last 7 days) against the mean/stddev of
    the preceding MIN_BASELINE_WINDOWS 7-day windows. Flags a candidate
    only if the deviation clears the lowest z-score band -- see
    _Z_SEVERITY_BANDS. Requires at least MIN_BASELINE_WINDOWS historical
    windows with revenue > 0; otherwise this business doesn't have enough
    history yet and the detector produces nothing (requirement #11 --
    graceful, not a guess dressed up as a fixed-threshold alert).
    """
    reference = today or date.today()
    current_start = reference - timedelta(days=6)
    current = _period_totals(db, business, current_start, reference)

    history_windows = _consecutive_windows(current_start - timedelta(days=1), 7, MIN_BASELINE_WINDOWS)
    history_revenues = [_period_totals(db, business, s, e)["revenue"] for s, e in history_windows]
    non_zero_revenues = [r for r in history_revenues if r > 0]
    if len(non_zero_revenues) < MIN_BASELINE_WINDOWS:
        return []

    values = [float(r) for r in history_revenues]
    baseline_mean = statistics.mean(values)
    baseline_stddev = statistics.pstdev(values)
    current_revenue = float(current["revenue"])

    if baseline_stddev == 0:
        if current_revenue == baseline_mean:
            return []
        z_score = 4.0 if current_revenue != baseline_mean else 0.0  # any deviation from a flat history is notable
    else:
        z_score = (current_revenue - baseline_mean) / baseline_stddev

    severity = _severity_from_bands(abs(z_score), _Z_SEVERITY_BANDS)
    if severity is None:
        return []

    direction = "low" if current_revenue < baseline_mean else "high"
    alert_type = f"{direction}_sales"
    supporting_values = {
        "method": "statistical_baseline",
        "baseline_mean_revenue": round(baseline_mean, 2),
        "baseline_stddev_revenue": round(baseline_stddev, 2),
        "baseline_window_count": len(history_windows),
        "observed_revenue": float(current["revenue"]),
        "z_score": round(z_score, 2),
    }
    week_bucket = reference.isocalendar()[:2]  # (iso_year, iso_week) -- dedupes same-week reruns
    return [
        AlertCandidate(
            alert_type=alert_type,
            severity=severity,
            title=f"Unusually {direction} sales this week",
            message=(
                f"Revenue for {current_start.isoformat()} to {reference.isoformat()} was "
                f"₦{current['revenue']:,.2f}, compared to a usual (baseline) weekly average of "
                f"₦{baseline_mean:,.2f} over the past {len(history_windows)} weeks -- "
                f"a {abs(z_score):.1f} standard-deviation {direction} deviation."
            ),
            affected_metric="revenue",
            period_start=current_start,
            period_end=reference,
            supporting_values=supporting_values,
            dedupe_key=f"{alert_type}:business:{week_bucket[0]}-W{week_bucket[1]:02d}",
        )
    ]


# ---------------------------------------------------------------------------
# Detector 2: significant revenue or profit changes (period-over-period)
# ---------------------------------------------------------------------------


def detect_revenue_profit_change(
    db: Session, business: Business, today: date | None = None, window_days: int = 30
) -> list[AlertCandidate]:
    """
    Compares the last `window_days` days against the preceding
    `window_days` days for both revenue and gross profit. This is a
    direct period-over-period percentage change (not a statistical
    baseline) -- for "how much did this actually change", a plain
    percentage is the clearer, more literal answer than a z-score, and
    doesn't require a deep transaction history to be meaningful.
    """
    reference = today or date.today()
    current_start = reference - timedelta(days=window_days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)

    current = _period_totals(db, business, current_start, reference)
    previous = _period_totals(db, business, previous_start, previous_end)

    if previous["transaction_count"] == 0:
        # No prior period to compare against -- graceful skip, not a
        # misleading "infinite % change" alert.
        return []

    month_bucket = reference.strftime("%Y-%m")
    candidates: list[AlertCandidate] = []

    for metric, label in (("revenue", "Revenue"), ("gross_profit", "Gross profit")):
        change_pct = _pct_change(previous[metric], current[metric])
        if change_pct is None:
            continue
        severity = _severity_from_bands(abs(float(change_pct)), _PCT_SEVERITY_BANDS)
        if severity is None:
            continue
        direction = "increased" if change_pct >= 0 else "decreased"
        alert_type = f"{metric}_change"
        candidates.append(
            AlertCandidate(
                alert_type=alert_type,
                severity=severity,
                title=f"{label} {direction} {abs(float(change_pct)):.0f}%",
                message=(
                    f"{label} for the last {window_days} days was ₦{current[metric]:,.2f}, "
                    f"versus ₦{previous[metric]:,.2f} in the previous {window_days} days -- "
                    f"a {abs(float(change_pct)):.1f}% {direction[:-1]}."
                ),
                affected_metric=metric,
                period_start=current_start,
                period_end=reference,
                supporting_values={
                    "method": "period_over_period",
                    "current_value": float(current[metric]),
                    "previous_value": float(previous[metric]),
                    "change_pct": float(change_pct),
                    "window_days": window_days,
                },
                dedupe_key=f"{alert_type}:business:{month_bucket}",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Detector 3: falling profit margins (trend)
# ---------------------------------------------------------------------------


def detect_falling_profit_margin(
    db: Session, business: Business, today: date | None = None
) -> list[AlertCandidate]:
    """
    Looks at profit margin over the last MIN_BASELINE_WINDOWS 7-day
    windows. Flags a candidate only if the trend is monotonically
    non-increasing (each week's margin no better than the one before,
    allowing a small epsilon for rounding noise) AND the total drop from
    the first to the last window is at least the lowest severity band --
    a single bad week isn't a trend; a sustained decline is.
    """
    reference = today or date.today()
    windows = _consecutive_windows(reference, 7, MIN_BASELINE_WINDOWS)
    period_data = [_period_totals(db, business, s, e) for s, e in windows]

    if any(p["transaction_count"] == 0 for p in period_data):
        # A week with zero transactions makes "margin" undefined for that
        # week -- not enough continuous data to call this a trend.
        return []

    margins = [float(p["profit_margin"]) for p in period_data]
    epsilon = 0.01
    is_non_increasing = all(margins[i] <= margins[i - 1] + epsilon for i in range(1, len(margins)))
    total_drop = margins[0] - margins[-1]

    if not is_non_increasing or total_drop <= 0:
        return []

    severity = _severity_from_bands(total_drop, _PCT_SEVERITY_BANDS)
    if severity is None:
        return []

    week_bucket = reference.isocalendar()[:2]
    return [
        AlertCandidate(
            alert_type="falling_profit_margin",
            severity=severity,
            title=f"Profit margin has fallen {total_drop:.1f} points over {len(windows)} weeks",
            message=(
                f"Profit margin has declined every week for the last {len(windows)} weeks, from "
                f"{margins[0]:.1f}% to {margins[-1]:.1f}% -- a {total_drop:.1f} percentage-point drop."
            ),
            affected_metric="profit_margin",
            period_start=windows[0][0],
            period_end=windows[-1][1],
            supporting_values={
                "method": "consecutive_weekly_trend",
                "weekly_margins_pct": [round(m, 2) for m in margins],
                "total_drop_pct_points": round(total_drop, 2),
            },
            dedupe_key=f"falling_profit_margin:business:{week_bucket[0]}-W{week_bucket[1]:02d}",
        )
    ]


DETECTORS: dict[str, Callable[..., list[AlertCandidate]]] = {
    "unusual_sales": detect_unusual_sales,
    "revenue_profit_change": detect_revenue_profit_change,
    "falling_profit_margin": detect_falling_profit_margin,
}
