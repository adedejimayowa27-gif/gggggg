"""
Pydantic schemas for the Business Decision Simulator (Step 7).

`ScenarioType` and `ScopeType` are the two enums the whole feature keys
off. `ScenarioParameters` is deliberately the one shape shared by all 4
scenario types this batch supports (selling_price_change,
cost_price_change, demand_change, sales_volume_change) -- they all boil
down to "change this one variable by a percentage, for this scope".
A future scenario type with a genuinely different shape (e.g. a
staffing scenario needing a headcount and a monthly cost) gets its own
parameters schema later; nothing here has to change to allow that.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioType(str, Enum):
    SELLING_PRICE_CHANGE = "selling_price_change"
    COST_PRICE_CHANGE = "cost_price_change"
    DEMAND_CHANGE = "demand_change"
    SALES_VOLUME_CHANGE = "sales_volume_change"


class ScopeType(str, Enum):
    BUSINESS = "business"
    CATEGORY = "category"
    PRODUCT = "product"


class ScenarioParameters(BaseModel):
    """
    What every one of this batch's 4 scenario types needs: which slice of
    the business the change applies to, and by how much.

    change_percentage is signed -- +8 means "increase by 8%", -15 means
    "decrease by 15%" -- matching every example in the Step 7 spec
    ("Increase Rice price by 8%", "Sales decrease by 15%", etc.) exactly.
    """

    scope_type: ScopeType
    # Required when scope_type is "category" or "product" (the specific
    # category/product name); must be omitted when scope_type is
    # "business" (a business-wide change has no single target).
    scope_value: str | None = None
    change_percentage: Decimal = Field(..., description="Signed percentage, e.g. 8 or -15.")

    @model_validator(mode="after")
    def _validate_scope_value(self) -> "ScenarioParameters":
        if self.scope_type == ScopeType.BUSINESS and self.scope_value is not None:
            raise ValueError("scope_value must not be set when scope_type is 'business'.")
        if self.scope_type != ScopeType.BUSINESS and not self.scope_value:
            raise ValueError(f"scope_value is required when scope_type is {self.scope_type.value!r}.")
        return self


class ScenarioMetrics(BaseModel):
    """Revenue/cost/profit/margin for one side of a comparison (current or simulated)."""

    revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    profit_margin: Decimal
    units_sold: Decimal


class ScenarioDiff(BaseModel):
    """Simulated minus current, plus percentage change, for each metric."""

    revenue_change: Decimal
    revenue_change_pct: Decimal | None
    total_cost_change: Decimal
    total_cost_change_pct: Decimal | None
    gross_profit_change: Decimal
    gross_profit_change_pct: Decimal | None
    profit_margin_change: Decimal  # percentage-point difference, not a % change of a %


class SimulationResults(BaseModel):
    current: ScenarioMetrics
    simulated: ScenarioMetrics
    diff: ScenarioDiff


class SimulationRunIn(BaseModel):
    """Body for POST /simulate (a live preview -- nothing is saved)."""

    scenario_type: ScenarioType
    parameters: ScenarioParameters
    baseline_start_date: date
    baseline_end_date: date


class SimulationRunOut(BaseModel):
    """Response for POST /simulate -- everything a saved Simulation has, minus persistence fields."""

    scenario_type: ScenarioType
    parameters: ScenarioParameters
    baseline_start_date: date
    baseline_end_date: date
    assumptions: list[str]
    results: SimulationResults


class SimulationCreateIn(SimulationRunIn):
    """Body for POST /simulations -- same inputs as a preview, plus a name to save it under."""

    name: str = Field(..., min_length=1, max_length=255)


class SimulationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    scenario_type: ScenarioType
    parameters: ScenarioParameters
    baseline_start_date: date
    baseline_end_date: date
    assumptions: list[str]
    results: SimulationResults
    created_at: datetime


class SimulationListItem(BaseModel):
    """Slimmer shape for the list endpoint -- omits the full results/assumptions payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    scenario_type: ScenarioType
    parameters: ScenarioParameters
    baseline_start_date: date
    baseline_end_date: date
    created_at: datetime
