"""Schemas for the onboarding checklist and sample data (Step 13, Batch 4)."""
from pydantic import BaseModel


class OnboardingStatus(BaseModel):
    """Which getting-started steps the business's OWN data has completed
    (sample data never counts), and whether sample data is loaded."""

    add_sales: bool
    record_expense: bool
    track_stock: bool
    invite_team: bool
    has_sample_data: bool


class SampleDataLoaded(BaseModel):
    transactions: int
    expenses: int
    stock_records: int


class SampleDataRemoved(BaseModel):
    transactions: int
    expenses: int
    stock_records: int
    alerts: int
