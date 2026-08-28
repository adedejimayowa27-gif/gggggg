"""
Scenario calculation engine (Step 7 -- Business Decision Simulator).

Pure computation: given a business's real historical transactions in a
date range plus a scenario definition, computes ScenarioMetrics for the
unmodified ("current") data and for the scenario-adjusted ("simulated")
data, and returns both plus the diff. This module never writes to the
database and never mutates a real Transaction row -- it reads
transactions once (read-only), builds a second, separate in-memory copy
with the scenario's effect applied, and aggregates both independently.
Nothing here is invented by an LLM; every number a route or the AI
assistant surfaces about a simulation comes from this module.

Registry design (requirement #12 -- future scenarios: staffing,
inventory, promotions, rent, new branches): SCENARIO_HANDLERS maps a
ScenarioType to a handler function. All 4 scenario types this batch
supports reduce to the same shape -- "scale one per-row field by a
percentage, for a given scope" -- so they share two small handler
functions (_apply_price_change, _apply_volume_change). A structurally
different future scenario (e.g. a fixed monthly rent figure with no
per-transaction basis at all) would get its own handler with a
completely different internal shape; only SCENARIO_HANDLERS and
_VARIABLE_LABELS need a new entry, nothing else in this module, the
routes, or the Simulation model changes.

Modeling choice worth knowing: demand_change and sales_volume_change are
computed identically (both scale units sold; price fields untouched).
The underlying transaction data has no way to distinguish "demand" from
"what was actually sold" -- there's no stockout/conversion tracking --
so the most honest interpretation of a demand change, absent that data,
is exactly a proportional scaling of recorded units. This is stated
explicitly in build_assumptions() rather than left implicit.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable, Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.business import Business
from app.models.transaction import Transaction
from app.schemas.simulation import (
    ScenarioDiff,
    ScenarioMetrics,
    ScenarioParameters,
    ScenarioType,
    ScopeType,
    SimulationResults,
)

# A change_percentage of exactly -100 is meaningful ("reduce to zero" --
# e.g. "sales volume decreases by 100%" = stop selling entirely). Anything
# below that would flip the affected field negative, which has no
# business meaning for a price or a quantity.
_MIN_CHANGE_PERCENTAGE = Decimal(-100)


@dataclass(frozen=True)
class _Row:
    """
    One transaction's fields needed for scenario math. Deliberately a
    minimal, plain dataclass rather than the full ORM object -- a handler
    can only ever see/adjust these five fields (never business_id, never
    anything that would let a scenario "leak" into real data), and a
    handler can be unit-tested by constructing _Row instances directly,
    with no DB session required.
    """

    product: str
    category: str | None
    quantity: Decimal
    selling_price: Decimal
    cost_price: Decimal


def _matches_scope(row: _Row, params: ScenarioParameters) -> bool:
    if params.scope_type == ScopeType.BUSINESS:
        return True
    target = (params.scope_value or "").strip().lower()
    if params.scope_type == ScopeType.PRODUCT:
        return row.product.strip().lower() == target
    if params.scope_type == ScopeType.CATEGORY:
        return (row.category or "").strip().lower() == target
    return False


def _aggregate(rows: Sequence[_Row]) -> ScenarioMetrics:
    revenue = sum((r.quantity * r.selling_price for r in rows), Decimal(0))
    total_cost = sum((r.quantity * r.cost_price for r in rows), Decimal(0))
    units_sold = sum((r.quantity for r in rows), Decimal(0))
    gross_profit = revenue - total_cost
    profit_margin = (gross_profit / revenue * 100) if revenue > 0 else Decimal(0)
    return ScenarioMetrics(
        revenue=revenue,
        total_cost=total_cost,
        gross_profit=gross_profit,
        profit_margin=profit_margin,
        units_sold=units_sold,
    )


def _apply_price_change(
    rows: Sequence[_Row], params: ScenarioParameters, field: str
) -> list[_Row]:
    """
    Shared by selling_price_change and cost_price_change: multiply the
    given per-unit price field by (1 + change_percentage/100) for rows
    matching scope; rows outside scope are returned completely
    unchanged. `field` is "selling_price" or "cost_price".
    """
    factor = Decimal(1) + params.change_percentage / Decimal(100)
    adjusted = []
    for row in rows:
        if _matches_scope(row, params):
            if field == "selling_price":
                row = _Row(row.product, row.category, row.quantity, row.selling_price * factor, row.cost_price)
            else:
                row = _Row(row.product, row.category, row.quantity, row.selling_price, row.cost_price * factor)
        adjusted.append(row)
    return adjusted


def _apply_volume_change(rows: Sequence[_Row], params: ScenarioParameters) -> list[_Row]:
    """
    Shared by demand_change and sales_volume_change: multiply quantity by
    (1 + change_percentage/100) for rows matching scope; price fields are
    never touched. See this module's docstring for why these two
    scenario types are modeled identically.
    """
    factor = Decimal(1) + params.change_percentage / Decimal(100)
    adjusted = []
    for row in rows:
        if _matches_scope(row, params):
            row = _Row(row.product, row.category, row.quantity * factor, row.selling_price, row.cost_price)
        adjusted.append(row)
    return adjusted


SCENARIO_HANDLERS: dict[ScenarioType, Callable[[Sequence[_Row], ScenarioParameters], list[_Row]]] = {
    ScenarioType.SELLING_PRICE_CHANGE: lambda rows, params: _apply_price_change(rows, params, "selling_price"),
    ScenarioType.COST_PRICE_CHANGE: lambda rows, params: _apply_price_change(rows, params, "cost_price"),
    ScenarioType.DEMAND_CHANGE: _apply_volume_change,
    ScenarioType.SALES_VOLUME_CHANGE: _apply_volume_change,
}

_VARIABLE_LABELS: dict[ScenarioType, str] = {
    ScenarioType.SELLING_PRICE_CHANGE: "selling price",
    ScenarioType.COST_PRICE_CHANGE: "cost price",
    ScenarioType.DEMAND_CHANGE: "demand (units sold)",
    ScenarioType.SALES_VOLUME_CHANGE: "sales volume (units sold)",
}


def _pct_change(old: Decimal, new: Decimal) -> Decimal | None:
    if old == 0:
        return None
    return (new - old) / abs(old) * 100


def _scope_description(params: ScenarioParameters) -> str:
    if params.scope_type == ScopeType.BUSINESS:
        return "the whole business"
    if params.scope_type == ScopeType.PRODUCT:
        return f"the product {params.scope_value!r}"
    return f"the {params.scope_value!r} category"


def build_assumptions(
    scenario_type: ScenarioType, params: ScenarioParameters, start_date: date, end_date: date
) -> list[str]:
    """
    Plain-language description of exactly what a scenario assumes --
    requirement #9. Pure function of the scenario definition alone (no DB
    access), so it can describe a scenario before it's actually run (a
    live "here's what this will assume" preview in the UI). run_scenario()
    calls this and may append further, data-dependent assumptions (e.g.
    "no transactions matched this scope") that only become knowable once
    the real data has actually been read.
    """
    direction = "increases" if params.change_percentage >= 0 else "decreases"
    magnitude = abs(params.change_percentage)
    assumptions = [
        f"Based on actual transactions from {start_date.isoformat()} to {end_date.isoformat()}.",
        f"Assumes {_VARIABLE_LABELS[scenario_type]} {direction} by {magnitude}% for "
        f"{_scope_description(params)}; everything else in that period is held at its actual "
        "recorded values.",
    ]
    if params.scope_type != ScopeType.BUSINESS:
        assumptions.append(
            "Products/categories outside this scope are assumed completely unaffected by this change."
        )
    if scenario_type in (ScenarioType.SELLING_PRICE_CHANGE, ScenarioType.COST_PRICE_CHANGE):
        assumptions.append(
            "Units sold are assumed unchanged -- this scenario does not model any demand response "
            "to the price change (e.g. customers buying less because a price went up)."
        )
    if scenario_type in (ScenarioType.DEMAND_CHANGE, ScenarioType.SALES_VOLUME_CHANGE):
        assumptions.append(
            "Selling price and cost price per unit are assumed unchanged -- only the quantity sold "
            "is adjusted. Demand and sales volume are modeled identically here, since historical "
            "data only records units actually sold, not separate demand."
        )
    return assumptions


def run_scenario(
    db: Session,
    business: Business,
    scenario_type: ScenarioType,
    parameters: ScenarioParameters,
    start_date: date,
    end_date: date,
) -> tuple[SimulationResults, list[str]]:
    """
    The one entry point every route and AI tool calls to actually run a
    scenario. Reads this business's real transactions in [start_date,
    end_date] (read-only, one query), computes current vs simulated
    metrics, and returns (results, assumptions) -- assumptions includes
    everything from build_assumptions() plus any data-dependent facts
    (zero transactions in range at all, or zero transactions matching a
    product/category scope) discovered while actually reading the data.

    Never writes anything. The `rows` list built here is a plain Python
    copy of the fields needed for the math -- the real Transaction rows
    in the database are never touched, referenced for writing, or at
    risk of being modified by anything in this function.
    """
    if end_date < start_date:
        raise ValidationError("end_date must not be before start_date.")
    if parameters.change_percentage <= _MIN_CHANGE_PERCENTAGE:
        raise ValidationError(
            f"change_percentage must be greater than {_MIN_CHANGE_PERCENTAGE} "
            "(a decrease of 100% or more would make a price or quantity negative)."
        )

    handler = SCENARIO_HANDLERS.get(scenario_type)
    if handler is None:
        raise ValidationError(f"Unsupported scenario_type: {scenario_type!r}.")

    db_rows = (
        db.query(
            Transaction.product,
            Transaction.category,
            Transaction.quantity,
            Transaction.selling_price,
            Transaction.cost_price,
        )
        .filter(
            Transaction.business_id == business.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .all()
    )
    rows = [
        _Row(
            product=r.product,
            category=r.category,
            quantity=Decimal(r.quantity),
            selling_price=Decimal(r.selling_price),
            cost_price=Decimal(r.cost_price or 0),
        )
        for r in db_rows
    ]

    assumptions = build_assumptions(scenario_type, parameters, start_date, end_date)

    if not rows:
        assumptions.append(
            f"No transactions were found for this business between {start_date.isoformat()} and "
            f"{end_date.isoformat()} -- both the current and simulated figures below are zero "
            "because there is nothing to calculate from."
        )
    elif parameters.scope_type != ScopeType.BUSINESS and not any(
        _matches_scope(row, parameters) for row in rows
    ):
        assumptions.append(
            f"No transactions in this date range matched {_scope_description(parameters)} -- this "
            "simulation has no effect, so the current and simulated figures below are identical."
        )

    current = _aggregate(rows)
    simulated_rows = handler(rows, parameters)
    simulated = _aggregate(simulated_rows)

    diff = ScenarioDiff(
        revenue_change=simulated.revenue - current.revenue,
        revenue_change_pct=_pct_change(current.revenue, simulated.revenue),
        total_cost_change=simulated.total_cost - current.total_cost,
        total_cost_change_pct=_pct_change(current.total_cost, simulated.total_cost),
        gross_profit_change=simulated.gross_profit - current.gross_profit,
        gross_profit_change_pct=_pct_change(current.gross_profit, simulated.gross_profit),
        profit_margin_change=simulated.profit_margin - current.profit_margin,
    )
    results = SimulationResults(current=current, simulated=simulated, diff=diff)
    return results, assumptions
