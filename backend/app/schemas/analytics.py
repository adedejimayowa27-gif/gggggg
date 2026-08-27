"""
Pydantic schemas for analytics endpoints.
"""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    start_date: date
    end_date: date

    revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    profit_margin: Decimal  # percentage, e.g. 23.45 means 23.45%

    units_sold: Decimal
    transaction_count: int
    average_transaction_value: Decimal


class TimeseriesPoint(BaseModel):
    period_start: date
    revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal


class AnalyticsTimeseries(BaseModel):
    start_date: date
    end_date: date
    granularity: str
    points: list[TimeseriesPoint]


class ProductAnalyticsItem(BaseModel):
    product: str
    units_sold: Decimal
    revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    transaction_count: int


class ProductAnalytics(BaseModel):
    start_date: date
    end_date: date
    top_selling: list[ProductAnalyticsItem]
    highest_profit: list[ProductAnalyticsItem]
    lowest_profit: list[ProductAnalyticsItem]
    slow_moving: list[ProductAnalyticsItem]


class BreakdownItem(BaseModel):
    group: str
    units_sold: Decimal
    revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    transaction_count: int


class AnalyticsBreakdown(BaseModel):
    """
    Batch 6.5: revenue/cost/profit grouped by an optional field
    (category/customer/payment_method). `has_data` is false when the
    business has never populated this field on any transaction in range
    -- distinct from a legitimate "everything fell in one group" result --
    so a consumer (dashboard chart or the AI assistant) can say "this
    business doesn't track payment method data" instead of rendering a
    single misleading bucket.
    """

    start_date: date
    end_date: date
    group_by: str
    items: list[BreakdownItem]
    has_data: bool
