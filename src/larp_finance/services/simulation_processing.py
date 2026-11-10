from sqlalchemy import select
from sqlalchemy.orm import Session

from larp_finance.models import Asset, Simulation
from larp_finance.services.historical_prices import (
    HistoricalPriceProvider,
)
from larp_finance.services.simulation_service import (
    run_buy_and_hold_simulation,
)


def process_simulation(
    db: Session,
    simulation_id: int,
    provider: HistoricalPriceProvider,
) -> None:

    # Step 1: Lock the simulation while claiming it.
    simulation = db.scalar(
        select(Simulation)
        .where(Simulation.id == simulation_id)
        .with_for_update()
    )

    if simulation is None:
        db.rollback()
        raise ValueError("Simulation not found")

    # Do not process an already claimed or completed job.
    if simulation.status != "pending":
        db.rollback()
        return

    simulation.status = "running"
    db.commit()

    try:
        # Step 2: Load the associated asset.
        asset = db.get(Asset, simulation.asset_id)

        if asset is None:
            raise ValueError("Simulation asset not found")

        # Step 3: Perform the historical calculation.
        result = run_buy_and_hold_simulation(
            provider=provider,
            symbol=asset.symbol,
            asset_type=asset.asset_type,
            initial_investment=simulation.initial_investment,
            purchase_date=simulation.purchase_date,
            valuation_date=simulation.valuation_date,
        )

        # Step 4: Save the calculation results.
        simulation.purchase_price = result.purchase_price
        simulation.final_price = result.final_price
        simulation.final_value = result.final_value
        simulation.profit_loss = result.profit_loss
        simulation.error_message = None
        simulation.status = "completed"

        db.commit()

    except Exception as exc:
        # Discard any unsuccessful database changes.
        db.rollback()

        # Record the failure without exposing internal details.
        simulation = db.get(Simulation, simulation_id)

        if simulation is not None:
            simulation.status = "failed"
            simulation.error_message = (
                f"{type(exc).__name__}: Simulation processing failed"
            )
            db.commit()

        raise
