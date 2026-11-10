from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from larp_finance.auth import get_current_user
from larp_finance.database import get_db
from larp_finance.models import Asset, Simulation, User
from larp_finance.schemas import SimulationCreate, SimulationResponse


router = APIRouter(
    prefix="/simulations",
    tags=["Simulations"],
)


@router.post(
    "",
    response_model=SimulationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_simulation(
    simulation_data: SimulationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Step 1: Validate the purchase date.
    if simulation_data.purchase_date >= date.today():
        raise HTTPException(
            status_code=422,
            detail="Purchase date must be in the past",
        )
    
    if simulation_data.valuation_date > date.today():
        raise HTTPException(
            status_code=422,
            detail="Valuation date cannot be in the future",
        )

    if simulation_data.valuation_date <= simulation_data.purchase_date:
        raise HTTPException(
            status_code=422,
            detail="Valuation date must be after purchase date",
        )


    # Step 2: Check that the asset exists.
    asset = db.get(Asset, simulation_data.asset_id)

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    # Step 3: Create a pending simulation.
    simulation = Simulation(
        user_id=current_user.id,
        asset_id=asset.id,
        initial_investment=simulation_data.initial_investment,
        purchase_date=simulation_data.purchase_date,
        valuation_date=simulation_data.valuation_date,
        status="pending",
    )

    db.add(simulation)

    # Step 4: Save the simulation atomically.
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Simulation could not be created",
        )

    db.refresh(simulation)

    return simulation


@router.get(
    "/{simulation_id}",
    response_model=SimulationResponse,
)
def get_simulation(
    simulation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    simulation = db.scalar(
        select(Simulation).where(
            Simulation.id == simulation_id,
            Simulation.user_id == current_user.id,
        )
    )

    if simulation is None:
        raise HTTPException(
            status_code=404,
            detail="Simulation not found",
        )

    return simulation
