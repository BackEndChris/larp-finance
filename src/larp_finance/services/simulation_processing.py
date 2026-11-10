from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from larp_finance.models import Asset, Simulation
from larp_finance.services.historical_prices import HistoricalPriceProvider
from larp_finance.services.simulation_service import run_buy_and_hold_simulation
from larp_finance.services.historical_errors import HistoricalPriceError, TemporaryHistoricalPriceError


PROCESSING_LEASE = timedelta(minutes=10)
MAX_PROCESSING_ATTEMPTS = 3


def locked_simulation(db, simulation_id):
    return db.scalar(
        select(Simulation).where(Simulation.id == simulation_id)
        .with_for_update().execution_options(populate_existing=True)
    )


def clear_claim(simulation):
    simulation.processing_token = None
    simulation.lease_expires_at = None


def owns_claim(db, simulation, token):
    return (
        simulation is not None
        and simulation.status == "running"
        and simulation.processing_token == token
        and simulation.lease_expires_at is not None
        and simulation.lease_expires_at > db.scalar(select(func.clock_timestamp()))
    )


def process_simulation(
    db: Session,
    simulation_id: int,
    provider: HistoricalPriceProvider | None = None,
    *,
    provider_factory=None,
) -> None:
    token = str(uuid4())
    try:
        simulation = locked_simulation(db, simulation_id)
        if simulation is None:
            db.rollback()
            return
        now = db.scalar(select(func.clock_timestamp()))
        if not (
            (simulation.status == "pending" and (
                simulation.retry_not_before is None or simulation.retry_not_before <= now
            ))
            or (simulation.status == "running" and (
                simulation.lease_expires_at is None or simulation.lease_expires_at <= now
            ))
        ):
            db.rollback()
            return
        if simulation.processing_attempts >= MAX_PROCESSING_ATTEMPTS:
            simulation.status = "failed"
            simulation.error_message = "Simulation processing attempts exhausted"
            clear_claim(simulation)
            db.commit()
            return

        asset = db.get(Asset, simulation.asset_id)
        inputs = dict(
            symbol=asset.symbol,
            asset_type=asset.asset_type,
            initial_investment=simulation.initial_investment,
            purchase_date=simulation.purchase_date,
            valuation_date=simulation.valuation_date,
        )
        data_source = simulation.data_source
        simulation.status = "running"
        simulation.retry_not_before = None
        simulation.processing_attempts += 1
        simulation.processing_token = token
        simulation.lease_expires_at = now + PROCESSING_LEASE
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    # Only plain values cross this boundary: no open transaction during retrieval.
    try:
        if provider_factory is not None:
            provider = provider_factory(data_source=data_source, **inputs)
        result = run_buy_and_hold_simulation(provider=provider, **inputs)
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        try:
            simulation = locked_simulation(db, simulation_id)
            if owns_claim(db, simulation, token):
                if isinstance(exc, TemporaryHistoricalPriceError) and simulation.processing_attempts < MAX_PROCESSING_ATTEMPTS:
                    simulation.status = "pending"
                    simulation.next_dispatch_at = db.scalar(select(func.clock_timestamp())) + timedelta(seconds=exc.retry_after)
                    simulation.retry_not_before = simulation.next_dispatch_at
                else:
                    simulation.status = "failed"
                simulation.error_message = str(exc) if isinstance(exc, HistoricalPriceError) else f"{type(exc).__name__}: Simulation processing failed"
                clear_claim(simulation)
                db.commit()
            else:
                db.rollback()
        except SQLAlchemyError:
            db.rollback()
            raise
        raise

    try:
        simulation = locked_simulation(db, simulation_id)
        if not owns_claim(db, simulation, token):
            db.rollback()
            return
        simulation.purchase_price = result.purchase_price
        simulation.final_price = result.final_price
        simulation.final_value = result.final_value
        simulation.profit_loss = result.profit_loss
        simulation.actual_purchase_date = result.purchase_date
        simulation.actual_valuation_date = result.valuation_date
        simulation.error_message = None
        simulation.status = "completed"
        clear_claim(simulation)
        db.commit()
    except SQLAlchemyError:
        # An uncertain commit must not be converted into a calculation failure.
        db.rollback()
        raise
