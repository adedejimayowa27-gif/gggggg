"""
Simulation model.

Represents one saved "what if" scenario for a business (Step 7, the
Business Decision Simulator) -- e.g. "increase Rice price by 8%" or
"sales decrease by 15% business-wide". A simulation never touches real
Transaction rows; it's a stored record of a scenario definition plus the
already-computed comparison between the business's real historical
numbers and the projected numbers under that scenario.

Design choices worth knowing before touching this model:

- `scenario_type` is a plain string key (e.g. "selling_price_change"),
  not a DB enum. Step 7 initially supports 4 types (selling_price_change,
  cost_price_change, demand_change, sales_volume_change), but requirement
  #12 asks for a scenario engine future scenario types (staffing,
  inventory, promotions, rent, new branches) can plug into -- a plain
  string means adding a new scenario type later is a code change in the
  scenario engine (app.services.scenario_engine, Batch 7.2), not a
  migration.
- `parameters`, `assumptions`, and `results` are JSONB precisely because
  different scenario types need different shaped inputs and outputs (a
  price-change scenario's parameters look nothing like a future
  new-branch scenario's), the same reasoning already used for
  ImportSession's detected_columns/raw_rows/suggested_mapping. The 4
  variable types this batch supports all use the same parameters shape
  (see app.schemas.simulation for exactly what that shape is) -- that's
  a schema-layer convention, not a DB-layer constraint, so it can vary
  per scenario_type without another migration.
- baseline_start_date/baseline_end_date are real Date columns (not
  buried in JSON) since "what date range was this simulation based on"
  is exactly the kind of thing worth being able to query/filter on
  directly.
"""
import uuid
from datetime import date as date_type, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # User-supplied label, e.g. "Rice +8% price test". Required -- every
    # row in this table is a saved simulation (a live, unsaved preview
    # never reaches the DB at all; see the /simulate vs /simulations
    # routes in Batch 7.3).
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # e.g. "selling_price_change" | "cost_price_change" | "demand_change"
    # | "sales_volume_change" -- see app.services.scenario_engine for the
    # registry these dispatch through.
    scenario_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Scenario-type-specific inputs, e.g. {"scope_type": "product",
    # "scope_value": "Rice", "change_percentage": 8.0}. Shape validated
    # at the schema/route layer, not here.
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # The historical window the "current business" side of the
    # comparison was computed from.
    baseline_start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    baseline_end_date: Mapped[date_type] = mapped_column(Date, nullable=False)

    # Plain-language strings describing exactly what was assumed (e.g.
    # "Based on transactions from 2026-01-01 to 2026-01-31", "Only Rice's
    # selling price changes; all other products are unaffected") --
    # requirement #9 ("clearly show assumptions") is a first-class,
    # always-populated field, not something the UI has to reconstruct.
    assumptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # {"current": {...}, "simulated": {...}, "diff": {...}} -- see
    # app.schemas.simulation.SimulationResults for the exact shape.
    # Computed once by the scenario engine and stored, so revisiting a
    # saved simulation never re-runs the calculation against
    # since-changed transaction data.
    results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # One-way relationship, no back_populates -- same lightweight pattern
    # ChatConversation already uses for its business_id, rather than
    # adding a `simulations` collection to the Business model itself.
    business: Mapped["Business"] = relationship("Business")

    def __repr__(self) -> str:
        return f"<Simulation id={self.id} business_id={self.business_id} name={self.name!r}>"
