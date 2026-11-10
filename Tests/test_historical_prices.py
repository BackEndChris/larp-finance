from datetime import date
from decimal import Decimal

from larp_finance.services.fake_market_data import (
    FakeHistoricalPriceProvider,
)
from larp_finance.services.historical_prices import (
    HistoricalPriceProvider,
)


# Test 1: Retrieve historical prices

def test_get_historical_prices():
    provider = FakeHistoricalPriceProvider(
        prices={
            "AAPL": {
                date(2026, 1, 1): Decimal("100.00"),
                date(2026, 1, 2): Decimal("110.00"),
                date(2026, 1, 3): Decimal("120.00"),
            }
        }
    )

    result = provider.get_daily_closes(
        symbol="AAPL",
        asset_type="stock",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )

    assert len(result) == 2
    assert result[date(2026, 1, 1)] == Decimal("100.00")
    assert result[date(2026, 1, 2)] == Decimal("110.00")


# Test 2: Unknown asset

def test_unknown_asset_returns_empty_prices():
    provider = FakeHistoricalPriceProvider(prices={})

    result = provider.get_daily_closes(
        symbol="UNKNOWN",
        asset_type="stock",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
    )

    assert result == {}


# Test 3: Symbol normalization

def test_historical_price_symbol_normalization():
    provider = FakeHistoricalPriceProvider(
        prices={
            "BTC": {
                date(2026, 1, 1): Decimal("80000.00"),
            }
        }
    )

    result = provider.get_daily_closes(
        symbol="btc",
        asset_type="crypto",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )

    assert result[date(2026, 1, 1)] == Decimal("80000.00")


# Test 4: Provider implements interface

def test_fake_provider_implements_interface():
    def use_provider(
        provider: HistoricalPriceProvider,
    ) -> dict[date, Decimal]:
        return provider.get_daily_closes(
            symbol="AAPL",
            asset_type="stock",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
        )

    provider = FakeHistoricalPriceProvider(prices={})

    assert use_provider(provider) == {}
