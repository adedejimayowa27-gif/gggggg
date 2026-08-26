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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.db.session import get_db
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics import DateRangePreset, resolve_date_range

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
