"""
Analytics routes.

Nested under a specific business, same ownership-scoping pattern as
transactions.py -- every route depends on get_owned_business.

All figures are computed via SQL aggregation (SUM/COUNT in the DB), never
pulled into Python and summed in a loop, and never estimated by an LLM.
"""
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, func
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.db.session import get_db
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.analytics import (
    AnalyticsBreakdown,
    AnalyticsSummary,
    AnalyticsTimeseries,
    BreakdownItem,
    ProductAnalytics,
    ProductAnalyticsItem,
    TimeseriesPoint,
)
from app.services.analytics import (
    BREAKDOWN_UNSET_LABELS,
    BreakdownField,
    DateRangePreset,
    Granularity,
    resolve_date_range,
)

router = APIRouter(prefix="/businesses/{business_id}/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date)

    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    units_expr = func.coalesce(func.sum(Transaction.quantity), 0)
    count_expr = func.count(Transaction.id)

    row = (
        db.query(
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            units_expr.label("units_sold"),
            count_expr.label("transaction_count"),
        )
        .filter(
            Transaction.business_id == business.id,
            Transaction.date >= resolved_start,
            Transaction.date <= resolved_end,
        )
        .one()
    )

    revenue = Decimal(row.revenue)
    total_cost = Decimal(row.total_cost)
    units_sold = Decimal(row.units_sold)
    transaction_count = row.transaction_count

    gross_profit = revenue - total_cost
    profit_margin = (
        (gross_profit / revenue * 100) if revenue > 0 else Decimal(0)
    )
    average_transaction_value = (
        (revenue / transaction_count) if transaction_count > 0 else Decimal(0)
    )

    return AnalyticsSummary(
        start_date=resolved_start,
        end_date=resolved_end,
        revenue=revenue,
        total_cost=total_cost,
        gross_profit=gross_profit,
        profit_margin=profit_margin,
        units_sold=units_sold,
        transaction_count=transaction_count,
        average_transaction_value=average_transaction_value,
    )


@router.get("/timeseries", response_model=AnalyticsTimeseries)
def get_analytics_timeseries(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    granularity: Granularity = Query(default=Granularity.DAY),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date)

    # date_trunc buckets by the given granularity; cast back to Date so the
    # response schema (and the client) get plain dates, not timestamps.
    period_expr = func.date_trunc(granularity.value, Transaction.date).cast(Date)

    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )

    rows = (
        db.query(
            period_expr.label("period_start"),
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
        )
        .filter(
            Transaction.business_id == business.id,
            Transaction.date >= resolved_start,
            Transaction.date <= resolved_end,
        )
        .group_by(period_expr)
        .order_by(period_expr)
        .all()
    )

    points = [
        TimeseriesPoint(
            period_start=row.period_start,
            revenue=Decimal(row.revenue),
            total_cost=Decimal(row.total_cost),
            gross_profit=Decimal(row.revenue) - Decimal(row.total_cost),
        )
        for row in rows
    ]

    return AnalyticsTimeseries(
        start_date=resolved_start,
        end_date=resolved_end,
        granularity=granularity.value,
        points=points,
    )


@router.get("/products", response_model=ProductAnalytics)
def get_analytics_products(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date)

    units_expr = func.coalesce(func.sum(Transaction.quantity), 0)
    revenue_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.selling_price), 0
    )
    cost_expr = func.coalesce(
        func.sum(Transaction.quantity * Transaction.cost_price), 0
    )
    count_expr = func.count(Transaction.id)

    # Single grouped aggregation by product -- every per-product number
    # (units, revenue, cost, profit, count) comes from this one query.
    rows = (
        db.query(
            Transaction.product.label("product"),
            units_expr.label("units_sold"),
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            count_expr.label("transaction_count"),
        )
        .filter(
            Transaction.business_id == business.id,
            Transaction.date >= resolved_start,
            Transaction.date <= resolved_end,
        )
        .group_by(Transaction.product)
        .all()
    )

    items = [
        ProductAnalyticsItem(
            product=row.product,
            units_sold=Decimal(row.units_sold),
            revenue=Decimal(row.revenue),
            total_cost=Decimal(row.total_cost),
            gross_profit=Decimal(row.revenue) - Decimal(row.total_cost),
            transaction_count=row.transaction_count,
        )
        for row in rows
    ]

    # The aggregation already happened in SQL above; these are just four
    # small in-memory sorts/slices over the already-grouped result set,
    # not a re-derivation of the figures themselves.
    top_selling = sorted(items, key=lambda i: i.units_sold, reverse=True)[:limit]
    highest_profit = sorted(items, key=lambda i: i.gross_profit, reverse=True)[:limit]
    lowest_profit = sorted(items, key=lambda i: i.gross_profit)[:limit]
    slow_moving = sorted(items, key=lambda i: i.units_sold)[:limit]

    return ProductAnalytics(
        start_date=resolved_start,
        end_date=resolved_end,
        top_selling=top_selling,
        highest_profit=highest_profit,
        lowest_profit=lowest_profit,
        slow_moving=slow_moving,
    )


# Batch 6.5: category/customer/payment_method are optional (Batch 6.1),
# so this is a new, additive endpoint rather than a change to the three
# above -- a business that has never populated these fields gets
# has_data=False here and every existing endpoint's response shape is
# completely unaffected either way.
_GROUP_BY_COLUMNS = {
    BreakdownField.CATEGORY: Transaction.category,
    BreakdownField.CUSTOMER: Transaction.customer,
    BreakdownField.PAYMENT_METHOD: Transaction.payment_method,
}


@router.get("/breakdown", response_model=AnalyticsBreakdown)
def get_analytics_breakdown(
    group_by: BreakdownField = Query(...),
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date)
    group_column = _GROUP_BY_COLUMNS[group_by]

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
            group_column.label("group_value"),
            units_expr.label("units_sold"),
            revenue_expr.label("revenue"),
            cost_expr.label("total_cost"),
            count_expr.label("transaction_count"),
        )
        .filter(
            Transaction.business_id == business.id,
            Transaction.date >= resolved_start,
            Transaction.date <= resolved_end,
        )
        .group_by(group_column)
        .order_by(revenue_expr.desc())
        .limit(limit)
        .all()
    )

    # A non-null group_value on at least one row means this field is
    # genuinely tracked -- as opposed to every row being NULL, which means
    # the business has simply never populated it (see AnalyticsBreakdown's
    # docstring for why this distinction matters to the caller).
    has_data = any(row.group_value is not None for row in rows)
    unset_label = BREAKDOWN_UNSET_LABELS[group_by]

    items = [
        BreakdownItem(
            group=row.group_value if row.group_value else unset_label,
            units_sold=Decimal(row.units_sold),
            revenue=Decimal(row.revenue),
            total_cost=Decimal(row.total_cost),
            gross_profit=Decimal(row.revenue) - Decimal(row.total_cost),
            transaction_count=row.transaction_count,
        )
        for row in rows
    ]

    return AnalyticsBreakdown(
        start_date=resolved_start,
        end_date=resolved_end,
        group_by=group_by.value,
        items=items,
        has_data=has_data,
    )
