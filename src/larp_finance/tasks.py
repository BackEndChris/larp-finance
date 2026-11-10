import os
from decimal import Decimal

from larp_finance.celery_app import celery_app
from larp_finance.database import SessionLocal
from larp_finance.services.fake_market_data import FakeHistoricalPriceProvider
from larp_finance.services.simulation_processing import process_simulation


@celery_app.task
def add_numbers(a: int, b: int) -> int:
    return a + b


def build_simulation_provider(*, symbol, purchase_date, valuation_date, **unused):
    if os.getenv("LARP_SIMULATION_MODE") != "demo":
        raise ValueError("Historical simulation provider requires explicit demo mode")
    return FakeHistoricalPriceProvider(prices={symbol: {
        purchase_date: Decimal("100.00"),
        valuation_date: Decimal("120.00"),
    }})


@celery_app.task(acks_late=True, reject_on_worker_lost=False,
                 soft_time_limit=480, time_limit=540, ignore_result=True)
def process_simulation_task(simulation_id: int) -> None:
    with SessionLocal() as db:
        process_simulation(db, simulation_id, provider_factory=build_simulation_provider)
