"""
Simulation routes (Step 7 -- Business Decision Simulator).

Nested under a specific business so every route inherits the ownership
check from get_owned_business. POST /simulate is a live, unsaved preview
(nothing written to the DB); POST /simulations persists one under a name.
"""
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business, get_owned_simulation
from app.db.session import get_db
from app.models.business import Business
from app.models.simulation import Simulation
from app.schemas.simulation import (
    SimulationCreateIn,
    SimulationListItem,
    SimulationOut,
    SimulationRunIn,
    SimulationRunOut,
)
from app.services.scenario_engine import run_scenario

router = APIRouter(prefix="/businesses/{business_id}", tags=["simulations"])


@router.post("/simulate", response_model=SimulationRunOut)
def run_simulation_preview(
    payload: SimulationRunIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    results, assumptions = run_scenario(
        db, business, payload.scenario_type, payload.parameters,
        payload.baseline_start_date, payload.baseline_end_date,
    )
    return SimulationRunOut(
        scenario_type=payload.scenario_type,
        parameters=payload.parameters,
        baseline_start_date=payload.baseline_start_date,
        baseline_end_date=payload.baseline_end_date,
        assumptions=assumptions,
        results=results,
    )


@router.post("/simulations", response_model=SimulationOut, status_code=status.HTTP_201_CREATED)
def create_simulation(
    payload: SimulationCreateIn,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    results, assumptions = run_scenario(
        db, business, payload.scenario_type, payload.parameters,
        payload.baseline_start_date, payload.baseline_end_date,
    )
    simulation = Simulation(
        id=uuid.uuid4(),
        business_id=business.id,
        name=payload.name,
        scenario_type=payload.scenario_type.value,
        parameters=payload.parameters.model_dump(mode="json"),
        baseline_start_date=payload.baseline_start_date,
        baseline_end_date=payload.baseline_end_date,
        assumptions=assumptions,
        results=results.model_dump(mode="json"),
    )
    db.add(simulation)
    db.commit()
    db.refresh(simulation)
    return SimulationOut.model_validate(simulation)


@router.get("/simulations", response_model=list[SimulationListItem])
def list_simulations(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    simulations = (
        db.query(Simulation)
        .filter(Simulation.business_id == business.id)
        .order_by(Simulation.created_at.desc())
        .limit(limit)
        .all()
    )
    return [SimulationListItem.model_validate(s) for s in simulations]


@router.get("/simulations/{simulation_id}", response_model=SimulationOut)
def get_simulation(
    simulation_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    simulation = get_owned_simulation(simulation_id, business, db)
    return SimulationOut.model_validate(simulation)


@router.delete("/simulations/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_simulation(
    simulation_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    simulation = get_owned_simulation(simulation_id, business, db)
    db.delete(simulation)
    db.commit()
