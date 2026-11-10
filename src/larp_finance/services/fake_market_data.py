from datetime import date
from decimal import Decimal

from larp_finance.services.historical_prices import (
    HistoricalPriceProvider,
)


class FakeHistoricalPriceProvider(HistoricalPriceProvider):
    def __init__(
        self,
        prices: dict[str, dict[date, Decimal]],
    ):
        self.prices = prices

    def get_daily_closes(
        self,
        symbol: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        symbol = symbol.upper()

        asset_prices = self.prices.get(symbol, {})

        return {
            day: price
            for day, price in asset_prices.items()
            if start_date <= day <= end_date
        }
