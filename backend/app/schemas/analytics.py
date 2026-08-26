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
