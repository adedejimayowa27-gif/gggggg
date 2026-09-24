"""
Analytics routes.

Nested under a specific business, same ownership-scoping pattern as
transactions.py -- every route depends on get_owned_business.

All figures are computed via SQL aggregation (SUM/COUNT in the DB), never
pulled into Python and summed in a loop, and never estimated by an LLM.
"""
import uuid
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
    CustomerLoyalty,
    CustomerLoyaltySegment,
    ProductAnalytics,
    ProductAnalyticsItem,
    TimeseriesPoint,
)
from app.services.expenses import expense_filters, expense_total
from app.services.analytics import (
    BREAKDOWN_UNSET_LABELS,
    BreakdownField,
    DateRangePreset,
    Granularity,
    cost_expr,
    get_latest_transaction_date,
    period_filters,
    resolve_date_range,
    revenue_expr,
    transaction_count_expr,
    units_expr,
)

router = APIRouter(prefix="/businesses/{business_id}/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    anchor_today = get_latest_transaction_date(db, business) or date_type.today()
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date, today=anchor_today)

    row = (
        db.query(
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
            units_expr().label("units_sold"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, resolved_start, resolved_end, branch_id=branch_id))
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

    # Operating expenses for the same window (and branch, if one is chosen:
    # expenses with no branch are shared overhead, so they appear in the
    # whole-business view but not in a single branch's).
    operating_expenses, expense_count = expense_total(
        db, *expense_filters(business.id, resolved_start, resolved_end, branch_id=branch_id)
    )
    net_profit = gross_profit - operating_expenses
    net_profit_margin = (net_profit / revenue * 100) if revenue > 0 else Decimal(0)

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
        operating_expenses=operating_expenses,
        expense_count=expense_count,
        net_profit=net_profit,
        net_profit_margin=net_profit_margin,
    )


@router.get("/timeseries", response_model=AnalyticsTimeseries)
def get_analytics_timeseries(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    granularity: Granularity = Query(default=Granularity.DAY),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    anchor_today = get_latest_transaction_date(db, business) or date_type.today()
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date, today=anchor_today)

    # date_trunc buckets by the given granularity; cast back to Date so the
    # response schema (and the client) get plain dates, not timestamps.
    period_expr = func.date_trunc(granularity.value, Transaction.date).cast(Date)

    rows = (
        db.query(
            period_expr.label("period_start"),
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
        )
        .filter(*period_filters(business, resolved_start, resolved_end, branch_id=branch_id))
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
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    anchor_today = get_latest_transaction_date(db, business) or date_type.today()
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date, today=anchor_today)

    # Single grouped aggregation by product -- every per-product number
    # (units, revenue, cost, profit, count) comes from this one query.
    #
    # Step 11, Batch 11.7 (performance-at-scale audit note, not a fix):
    # this pulls every distinct product for the business into memory
    # before the four rankings below are sorted and sliced to `limit` in
    # Python -- correct today, but for a business with an unusually
    # large number of distinct product names, four separate queries
    # (one per ranking, each with its own ORDER BY + LIMIT pushed to the
    # database) would scale better than fetching everything up front.
    # Left as-is here since the current behavior is correct and this
    # audit's mandate is fixing bugs, not rewriting working endpoints --
    # worth revisiting if a business's distinct-product count ever
    # becomes large enough for this to show up in practice.
    rows = (
        db.query(
            Transaction.product.label("product"),
            units_expr().label("units_sold"),
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, resolved_start, resolved_end, branch_id=branch_id))
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
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    anchor_today = get_latest_transaction_date(db, business) or date_type.today()
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date, today=anchor_today)
    group_column = _GROUP_BY_COLUMNS[group_by]
    revenue_column = revenue_expr()

    rows = (
        db.query(
            group_column.label("group_value"),
            units_expr().label("units_sold"),
            revenue_column.label("revenue"),
            cost_expr().label("total_cost"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, resolved_start, resolved_end, branch_id=branch_id))
        .group_by(group_column)
        .order_by(revenue_column.desc())
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


@router.get("/customer-loyalty", response_model=CustomerLoyalty)
def get_customer_loyalty(
    range: DateRangePreset = Query(default=DateRangePreset.LAST_30D),
    start_date: date_type | None = Query(default=None),
    end_date: date_type | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None, description="Restrict to one branch."),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """
    New vs. returning customers in the period -- see CustomerLoyalty's
    docstring for the exact "new" vs "returning" definition.

    Two queries rather than one: first, each customer's aggregate
    within the period (this is exactly get_breakdown's per-customer
    query, unlimited); second, each of those same customers' truest
    first-ever transaction date with this business (not bounded to the
    period, since "have they bought before" requires looking before
    start_date). The classification itself -- and the revenue/profit
    summation per bucket -- happens in Python rather than SQL, since
    "GROUP BY whether a joined subquery column is before or after a
    parameter" is exactly the kind of conditional aggregation that gets
    fragile and dialect-specific in SQL for very little benefit here:
    real-world customer counts for this product's businesses are small
    enough that summing ~dozens-to-low-thousands of rows in Python is
    not a performance concern, and the logic is far easier to verify
    correct written this way.
    """
    anchor_today = get_latest_transaction_date(db, business) or date_type.today()
    resolved_start, resolved_end = resolve_date_range(range, start_date, end_date, today=anchor_today)

    period_rows = (
        db.query(
            Transaction.customer.label("customer"),
            revenue_expr().label("revenue"),
            cost_expr().label("total_cost"),
            transaction_count_expr().label("transaction_count"),
        )
        .filter(*period_filters(business, resolved_start, resolved_end, branch_id=branch_id))
        .filter(Transaction.customer.isnot(None))
        .group_by(Transaction.customer)
        .all()
    )

    has_data = len(period_rows) > 0

    def empty_segment() -> CustomerLoyaltySegment:
        return CustomerLoyaltySegment(
            customer_count=0, revenue=Decimal(0), gross_profit=Decimal(0), transaction_count=0
        )

    if not has_data:
        return CustomerLoyalty(
            start_date=resolved_start,
            end_date=resolved_end,
            has_data=False,
            new=empty_segment(),
            returning=empty_segment(),
        )

    customers_in_period = [row.customer for row in period_rows]

    # Each of those customers' true first-ever purchase date, unbounded
    # by the period -- a customer who bought once last year and again
    # this period is "returning" even though this period alone would
    # make them look brand new.
    first_purchase_dates = dict(
        db.query(Transaction.customer, func.min(Transaction.date))
        .filter(Transaction.business_id == business.id, Transaction.customer.in_(customers_in_period))
        .group_by(Transaction.customer)
        .all()
    )

    new_totals = {"revenue": Decimal(0), "total_cost": Decimal(0), "transaction_count": 0, "customer_count": 0}
    returning_totals = {"revenue": Decimal(0), "total_cost": Decimal(0), "transaction_count": 0, "customer_count": 0}

    for row in period_rows:
        first_date = first_purchase_dates.get(row.customer)
        bucket = new_totals if (first_date is None or first_date >= resolved_start) else returning_totals
        bucket["revenue"] += Decimal(row.revenue)
        bucket["total_cost"] += Decimal(row.total_cost)
        bucket["transaction_count"] += row.transaction_count
        bucket["customer_count"] += 1

    def finalize(totals: dict) -> CustomerLoyaltySegment:
        return CustomerLoyaltySegment(
            customer_count=totals["customer_count"],
            revenue=totals["revenue"],
            gross_profit=totals["revenue"] - totals["total_cost"],
            transaction_count=totals["transaction_count"],
        )

    return CustomerLoyalty(
        start_date=resolved_start,
        end_date=resolved_end,
        has_data=True,
        new=finalize(new_totals),
        returning=finalize(returning_totals),
    )
