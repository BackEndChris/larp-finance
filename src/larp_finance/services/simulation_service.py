from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from larp_finance.services.historical_prices import (
    HistoricalPriceProvider,
)
from larp_finance.services.price_selection import (
    select_purchase_price,
    select_valuation_price,
)
from larp_finance.services.simulation_engine import (
    calculate_buy_and_hold,
)


@dataclass(frozen=True)
class SimulationResult:
    purchase_date: date
    valuation_date: date
    purchase_price: Decimal
    final_price: Decimal
    quantity: Decimal
    final_value: Decimal
    profit_loss: Decimal


def run_buy_and_hold_simulation(
    provider: HistoricalPriceProvider,
    symbol: str,
    asset_type: str,
    initial_investment: Decimal,
    purchase_date: date,
    valuation_date: date,
) -> SimulationResult:

    if purchase_date >= valuation_date:
        raise ValueError(
            "Valuation date must be after purchase date"
        )

    prices = provider.get_daily_closes(
        symbol=symbol,
        asset_type=asset_type,
        start_date=purchase_date - timedelta(days=7),
        end_date=valuation_date + timedelta(days=7),
    )

    max_gap = timedelta(days=1 if asset_type == "crypto" else 7)
    actual_purchase_date, purchase_price = (
        select_purchase_price(
            prices,
            purchase_date,
            max_gap=max_gap,
        )
    )

    actual_valuation_date, final_price = (
        select_valuation_price(
            prices,
            valuation_date,
            max_gap=max_gap,
        )
    )

    if actual_purchase_date > actual_valuation_date:
        raise ValueError(
            "Purchase date is after available valuation date"
        )

    result = calculate_buy_and_hold(
        initial_investment=initial_investment,
        purchase_price=purchase_price,
        final_price=final_price,
    )

    return SimulationResult(
        purchase_date=actual_purchase_date,
        valuation_date=actual_valuation_date,
        purchase_price=purchase_price,
        final_price=final_price,
        quantity=result["quantity"],
        final_value=result["final_value"],
        profit_loss=result["profit_loss"],
    )
