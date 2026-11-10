import os
from decimal import Decimal

from larp_finance.celery_app import celery_app
from larp_finance.database import SessionLocal
from larp_finance.services.fake_market_data import FakeHistoricalPriceProvider
from larp_finance.services.simulation_processing import process_simulation
from larp_finance.services.historical_errors import HistoricalPriceError
from larp_finance.services.twelve_data import TwelveDataHistoricalPriceProvider


@celery_app.task
def add_numbers(a: int, b: int) -> int:
    return a + b


def configured_data_source():
    mode = os.getenv("LARP_SIMULATION_MODE")
    if mode not in ("demo", "real"):
        raise HistoricalPriceError("Historical simulation requires explicit demo or real mode")
    return "twelve_data" if mode == "real" else "demo"


def build_simulation_provider(*, symbol, purchase_date, valuation_date, data_source=None, **unused):
    source = data_source or configured_data_source()
    if source == "twelve_data":
        return TwelveDataHistoricalPriceProvider()
    if source != "demo":
        raise HistoricalPriceError("Unsupported historical simulation data source")
    return FakeHistoricalPriceProvider(prices={symbol: {
        purchase_date: Decimal("100.00"),
        valuation_date: Decimal("120.00"),
    }})


@celery_app.task(acks_late=True, reject_on_worker_lost=False,
                 soft_time_limit=480, time_limit=540, ignore_result=True)
def process_simulation_task(simulation_id: int) -> None:
    with SessionLocal() as db:
        process_simulation(db, simulation_id, provider_factory=build_simulation_provider)
