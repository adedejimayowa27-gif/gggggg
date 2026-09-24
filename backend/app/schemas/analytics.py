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

    # Step 13, Batch 2: operating expenses (rent, salaries, ...) recorded for
    # the same period, and what is left after them. `gross_profit` above is
    # unchanged (revenue minus the cost of the goods sold). When no expenses
    # are recorded, `operating_expenses` is 0, `net_profit` equals
    # `gross_profit`, and `expense_count` is 0 so a client can say so instead
    # of presenting the figure as final.
    operating_expenses: Decimal = Decimal(0)
    expense_count: int = 0
    net_profit: Decimal = Decimal(0)
    net_profit_margin: Decimal = Decimal(0)  # percentage of revenue


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


class CustomerLoyaltySegment(BaseModel):
    customer_count: int
    revenue: Decimal
    gross_profit: Decimal
    transaction_count: int


class CustomerLoyalty(BaseModel):
    """
    New vs. returning customers within the requested period.

    "Returning" means the customer's first-ever transaction with this
    business predates the period's start_date (they already existed as
    a customer coming in). "New" means their first-ever transaction
    falls inside the period. Same `has_data` convention as
    AnalyticsBreakdown: false when no transaction in range has a
    customer recorded at all, so a consumer can distinguish "this
    business doesn't track customer identity" from "every sale this
    period happened to be a new customer."
    """

    start_date: date
    end_date: date
    has_data: bool
    new: CustomerLoyaltySegment
    returning: CustomerLoyaltySegment
