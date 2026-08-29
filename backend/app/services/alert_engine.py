"""
Alert detection engine (Step 8 -- Business Intelligence Alert Engine).

Pure detection: reads a business's real historical transactions
(read-only, same as scenario_engine.py) and produces a list of
AlertCandidate objects -- nothing is persisted here. Batch 8.4's
orchestrator runs every registered detector, deduplicates against
existing alerts, assigns final severity, and writes Alert rows.

Registry design (requirement #12): DETECTORS maps an alert_type string
to a detector function. 8 detector functions are registered, covering
every detection type Step 8 asks for. Adding a new one later is a new
function plus one new registry entry -- nothing about this module's
shape, or any existing detector, changes.

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

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.transaction import Transaction
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
    related_transaction_id: str | None = None


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


# Minimum previous-period revenue for a product before its % change is
# considered meaningful -- avoids flagging a product that went from
# ₦50 to ₦200 (a "300% increase" that's really just noise).
MIN_PRODUCT_REVENUE_FOR_TREND = Decimal(1000)

# Minimum number of individual transactions in the baseline window
# before per-transaction outlier detection is trusted statistically.
MIN_TRANSACTIONS_FOR_OUTLIER_BASELINE = 10

# Cap on how many outlier-transaction candidates one run surfaces, so a
# genuinely chaotic period doesn't flood the alert list.
MAX_OUTLIER_CANDIDATES = 3


def _product_totals(db: Session, business: Business, start: date, end: date) -> dict[str, dict]:
    """Per-product revenue/cost/units/count for one window, weighted-avg
    cost price included since that's what the cost-change detector needs
    (total cost alone conflates a price change with a volume change)."""
    rows = (
        db.query(
            Transaction.product.label("product"),
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
            units_expr().label("units_sold"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, start, end))
        .group_by(Transaction.product)
        .all()
    )
    result = {}
    for row in rows:
        units = Decimal(row.units_sold)
        total_cost = Decimal(row.total_cost)
        result[row.product] = {
            "revenue": Decimal(row.revenue),
            "total_cost": total_cost,
            "units_sold": units,
            "transaction_count": row.transaction_count,
            "avg_cost_price": (total_cost / units) if units > 0 else Decimal(0),
        }
    return result


# ---------------------------------------------------------------------------
# Detector 4: fast-growing and slow-moving products
# ---------------------------------------------------------------------------


def detect_product_trends(
    db: Session, business: Business, today: date | None = None, window_days: int = 30
) -> list[AlertCandidate]:
    """
    Per-product revenue this window_days vs the previous window_days.
    Requires at least MIN_PRODUCT_REVENUE_FOR_TREND in the previous
    period before a product's % change counts -- a brand-new or
    negligible-volume product swinging wildly isn't a meaningful trend,
    it's just small numbers.
    """
    reference = today or date.today()
    current_start = reference - timedelta(days=window_days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)

    current = _product_totals(db, business, current_start, reference)
    previous = _product_totals(db, business, previous_start, previous_end)

    month_bucket = reference.strftime("%Y-%m")
    candidates: list[AlertCandidate] = []

    for product, prev_data in previous.items():
        if prev_data["revenue"] < MIN_PRODUCT_REVENUE_FOR_TREND:
            continue
        current_revenue = current.get(product, {}).get("revenue", Decimal(0))
        change_pct = _pct_change(prev_data["revenue"], current_revenue)
        if change_pct is None:
            continue
        severity = _severity_from_bands(abs(float(change_pct)), _PCT_SEVERITY_BANDS)
        if severity is None:
            continue

        is_growing = change_pct > 0
        alert_type = "fast_growing_product" if is_growing else "slow_moving_product"
        verb = "grown" if is_growing else "slowed down"
        candidates.append(
            AlertCandidate(
                alert_type=alert_type,
                severity=severity,
                title=f"{product} has {verb} {abs(float(change_pct)):.0f}%",
                message=(
                    f"{product}'s revenue over the last {window_days} days was ₦{current_revenue:,.2f}, "
                    f"versus ₦{prev_data['revenue']:,.2f} in the previous {window_days} days -- "
                    f"a {abs(float(change_pct)):.1f}% {'increase' if is_growing else 'decrease'}."
                ),
                affected_product=product,
                affected_metric="revenue",
                period_start=current_start,
                period_end=reference,
                supporting_values={
                    "method": "period_over_period",
                    "current_value": float(current_revenue),
                    "previous_value": float(prev_data["revenue"]),
                    "change_pct": float(change_pct),
                    "window_days": window_days,
                },
                dedupe_key=f"{alert_type}:{product}:{month_bucket}",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Detector 5: significant product cost changes
# ---------------------------------------------------------------------------


def detect_product_cost_change(
    db: Session, business: Business, today: date | None = None, window_days: int = 30
) -> list[AlertCandidate]:
    """
    Per-product weighted-average cost price this window_days vs the
    previous window_days -- deliberately cost PRICE per unit, not total
    cost, so a supplier price hike is distinguished from simply selling
    more units.
    """
    reference = today or date.today()
    current_start = reference - timedelta(days=window_days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)

    current = _product_totals(db, business, current_start, reference)
    previous = _product_totals(db, business, previous_start, previous_end)

    month_bucket = reference.strftime("%Y-%m")
    candidates: list[AlertCandidate] = []

    for product, prev_data in previous.items():
        if prev_data["avg_cost_price"] <= 0:
            continue
        current_cost = current.get(product, {}).get("avg_cost_price", Decimal(0))
        if current_cost <= 0:
            continue  # not sold in current window -- no basis for a cost comparison
        change_pct = _pct_change(prev_data["avg_cost_price"], current_cost)
        if change_pct is None:
            continue
        severity = _severity_from_bands(abs(float(change_pct)), _PCT_SEVERITY_BANDS)
        if severity is None:
            continue

        direction = "risen" if change_pct > 0 else "fallen"
        candidates.append(
            AlertCandidate(
                alert_type="product_cost_change",
                severity=severity,
                title=f"{product}'s cost price has {direction} {abs(float(change_pct)):.0f}%",
                message=(
                    f"{product}'s average cost price over the last {window_days} days was "
                    f"₦{current_cost:,.2f} per unit, versus ₦{prev_data['avg_cost_price']:,.2f} in the "
                    f"previous {window_days} days -- a {abs(float(change_pct)):.1f}% {direction[:-1]}. "
                    "This affects your margin even if you haven't changed your selling price."
                ),
                affected_product=product,
                affected_metric="cost_price",
                period_start=current_start,
                period_end=reference,
                supporting_values={
                    "method": "period_over_period_unit_cost",
                    "current_avg_cost_price": float(current_cost),
                    "previous_avg_cost_price": float(prev_data["avg_cost_price"]),
                    "change_pct": float(change_pct),
                    "window_days": window_days,
                },
                dedupe_key=f"product_cost_change:{product}:{month_bucket}",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Detector 6: unusual transaction patterns (single-transaction outliers)
# ---------------------------------------------------------------------------


def detect_unusual_transactions(
    db: Session,
    business: Business,
    today: date | None = None,
    recent_days: int = 7,
    baseline_days: int = 60,
) -> list[AlertCandidate]:
    """
    Flags individual transactions in the last `recent_days` whose revenue
    (quantity * selling_price) is a statistical outlier versus this
    business's own transaction-size baseline over the preceding
    `baseline_days` -- e.g. one sale far larger than anything typical,
    which could be a bulk order worth noticing, a pricing mistake, or a
    data-entry error. Requires at least
    MIN_TRANSACTIONS_FOR_OUTLIER_BASELINE baseline transactions;
    otherwise skips (too little history to know what's "typical" for
    this business). Caps output at MAX_OUTLIER_CANDIDATES, most extreme
    first, so a genuinely volatile period doesn't flood the alert list.
    """
    reference = today or date.today()
    recent_start = reference - timedelta(days=recent_days - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)

    baseline_rows = (
        db.query(Transaction.quantity, Transaction.selling_price)
        .filter(*period_filters(business, baseline_start, baseline_end))
        .all()
    )
    if len(baseline_rows) < MIN_TRANSACTIONS_FOR_OUTLIER_BASELINE:
        return []

    baseline_values = [float(r.quantity * r.selling_price) for r in baseline_rows]
    baseline_mean = statistics.mean(baseline_values)
    baseline_stddev = statistics.pstdev(baseline_values)

    recent_rows = (
        db.query(Transaction)
        .filter(*period_filters(business, recent_start, reference))
        .all()
    )

    scored = []
    for txn in recent_rows:
        value = float(txn.quantity * txn.selling_price)
        if baseline_stddev == 0:
            # A perfectly uniform baseline can't produce a real z-score,
            # but any deviation from it is still notable -- same
            # reasoning as detect_unusual_sales's zero-stddev case.
            if value == baseline_mean:
                continue
            z_score = 4.0 if value > baseline_mean else -4.0
        else:
            z_score = (value - baseline_mean) / baseline_stddev
        severity = _severity_from_bands(abs(z_score), _Z_SEVERITY_BANDS)
        if severity is not None:
            scored.append((abs(z_score), z_score, severity, txn, value))

    scored.sort(key=lambda item: item[0], reverse=True)

    candidates: list[AlertCandidate] = []
    for _, z_score, severity, txn, value in scored[:MAX_OUTLIER_CANDIDATES]:
        candidates.append(
            AlertCandidate(
                alert_type="unusual_transaction_pattern",
                severity=severity,
                title=f"Unusually large transaction: {txn.product}",
                message=(
                    f"A transaction on {txn.date.isoformat()} for {txn.product} was worth "
                    f"₦{value:,.2f} ({txn.quantity} units at ₦{txn.selling_price:,.2f}), compared to "
                    f"a typical transaction size of ₦{baseline_mean:,.2f} for this business -- "
                    f"a {abs(z_score):.1f} standard-deviation outlier."
                ),
                affected_product=txn.product,
                affected_metric="transaction_value",
                related_transaction_id=str(txn.id),
                period_start=recent_start,
                period_end=reference,
                supporting_values={
                    "method": "statistical_baseline",
                    "baseline_mean_transaction_value": round(baseline_mean, 2),
                    "baseline_stddev_transaction_value": round(baseline_stddev, 2),
                    "baseline_transaction_count": len(baseline_rows),
                    "observed_value": round(value, 2),
                    "z_score": round(z_score, 2),
                },
                dedupe_key=f"unusual_transaction_pattern:{txn.id}",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Detector 7: potential stock shortages -- graceful stub
# ---------------------------------------------------------------------------


def detect_stock_shortage(db: Session, business: Business, today: date | None = None) -> list[AlertCandidate]:
    """
    Always returns no candidates. The Transaction model (and the rest of
    this app) has no inventory/stock-on-hand field at all -- there is
    nothing to compute a shortage from. Rather than fabricate a shortage
    signal from proxy data (which would misrepresent what the business
    actually has in stock), this detector is a deliberate no-op, kept in
    the registry (requirement #12) so it's the one place to implement
    real stock-shortage detection once inventory tracking exists,
    without touching the orchestrator or any other detector. This is the
    "gracefully handle unavailable fields" requirement (#11) applied at
    the detector level: silence, not a guess.
    """
    return []


# ---------------------------------------------------------------------------
# Detector 8: forecasted revenue decline (simple internal trend projection)
# ---------------------------------------------------------------------------

# How many trailing weekly points feed the trend line -- 6 gives a
# reasonable signal without demanding months of history.
FORECAST_TREND_WINDOWS = 6


def _linear_projection(values: list[float]) -> tuple[float, float]:
    """Ordinary least-squares fit of values against 0..n-1; returns
    (slope, projected_next_value). No external stats/ML dependency --
    this is intentionally simple, see detect_forecast_revenue_decline's
    docstring for why."""
    n = len(values)
    xs = list(range(n))
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(values)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator
    intercept = mean_y - slope * mean_x
    projected = intercept + slope * n  # the next point after the observed range
    return slope, projected


def detect_forecast_revenue_decline(
    db: Session, business: Business, today: date | None = None
) -> list[AlertCandidate]:
    """
    IMPORTANT: this app has no dedicated forecasting feature/model. This
    detector fits a simple linear trend to the last FORECAST_TREND_WINDOWS
    weekly revenue totals and projects one week forward -- a deliberately
    basic, transparent projection, not a real forecasting system. Every
    alert this produces says so explicitly in its message and
    supporting_values (method: "internal_linear_trend_projection"), so
    it's never confused with a proper forecast.

    Only fires when the trend is actually declining (negative slope) and
    the projected next week is a meaningful drop from the recent average
    -- a flat or growing trend never triggers this detector.
    """
    reference = today or date.today()
    windows = _consecutive_windows(reference, 7, FORECAST_TREND_WINDOWS)
    period_data = [_period_totals(db, business, s, e) for s, e in windows]

    if any(p["transaction_count"] == 0 for p in period_data):
        return []  # a gap week makes the trend line unreliable

    revenues = [float(p["revenue"]) for p in period_data]
    slope, projected = _linear_projection(revenues)
    if slope >= 0:
        return []  # flat or growing -- nothing to warn about here

    recent_average = statistics.mean(revenues[-2:])  # smooth over the last 2 actual weeks
    projected = max(projected, 0.0)
    change_pct = _pct_change(Decimal(recent_average), Decimal(projected))
    if change_pct is None or change_pct >= 0:
        return []

    severity = _severity_from_bands(abs(float(change_pct)), _PCT_SEVERITY_BANDS)
    if severity is None:
        return []

    week_bucket = reference.isocalendar()[:2]
    return [
        AlertCandidate(
            alert_type="forecast_revenue_decline",
            severity=severity,
            title=f"Revenue trending down -- projected {abs(float(change_pct)):.0f}% lower next week",
            message=(
                f"Based on a simple internal trend projection (not a dedicated forecasting model) over "
                f"the last {FORECAST_TREND_WINDOWS} weeks, revenue is trending downward and next week is "
                f"projected at roughly ₦{projected:,.2f}, versus a recent average of "
                f"₦{recent_average:,.2f} -- about a {abs(float(change_pct)):.1f}% projected decline."
            ),
            affected_metric="revenue",
            period_start=windows[0][0],
            period_end=windows[-1][1],
            supporting_values={
                "method": "internal_linear_trend_projection",
                "weekly_revenue": [round(r, 2) for r in revenues],
                "trend_slope_per_week": round(slope, 2),
                "recent_average_revenue": round(recent_average, 2),
                "projected_next_week_revenue": round(projected, 2),
                "projected_change_pct": float(change_pct),
            },
            dedupe_key=f"forecast_revenue_decline:business:{week_bucket[0]}-W{week_bucket[1]:02d}",
        )
    ]


DETECTORS: dict[str, Callable[..., list[AlertCandidate]]] = {
    "unusual_sales": detect_unusual_sales,
    "revenue_profit_change": detect_revenue_profit_change,
    "falling_profit_margin": detect_falling_profit_margin,
    "product_trends": detect_product_trends,
    "product_cost_change": detect_product_cost_change,
    "unusual_transactions": detect_unusual_transactions,
    "stock_shortage": detect_stock_shortage,
    "forecast_revenue_decline": detect_forecast_revenue_decline,
}
