from datetime import date
from decimal import Decimal
from typing import Protocol


class HistoricalPriceProvider(Protocol):
    def get_daily_closes(
        self,
        symbol: str,
        asset_type: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        ...
