from datetime import date
from decimal import Decimal

import pytest

from larp_finance.services.fake_market_data import (
    FakeHistoricalPriceProvider,
)
from larp_finance.services.simulation_service import (
    run_buy_and_hold_simulation,
)


def sample_provider():
    return FakeHistoricalPriceProvider(
        prices={
            "AAPL": {
                date(2026, 1, 2): Decimal("100.00"),
                date(2026, 1, 5): Decimal("105.00"),
                date(2026, 1, 6): Decimal("120.00"),
            }
        }
    )


# Test 1: Complete buy-and-hold calculation

def test_complete_simulation():
    result = run_buy_and_hold_simulation(
        provider=sample_provider(),
        symbol="AAPL",
        asset_type="stock",
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
    )

    assert result.purchase_price == Decimal("100.00")
    assert result.final_price == Decimal("120.00")
    assert result.quantity == Decimal("10")
    assert result.final_value == Decimal("1200.00")
    assert result.profit_loss == Decimal("200.00")


# Test 2: Weekend purchase shifts to Monday

def test_weekend_purchase():
    result = run_buy_and_hold_simulation(
        provider=sample_provider(),
        symbol="AAPL",
        asset_type="stock",
        initial_investment=Decimal("1050.00"),
        purchase_date=date(2026, 1, 3),
        valuation_date=date(2026, 1, 6),
    )

    assert result.purchase_date == date(2026, 1, 5)
    assert result.purchase_price == Decimal("105.00")
    assert result.quantity == Decimal("10")
    assert result.final_value == Decimal("1200.00")
    assert result.profit_loss == Decimal("150.00")


# Test 3: Missing historical data

def test_missing_historical_data():
    provider = FakeHistoricalPriceProvider(prices={})

    with pytest.raises(
        ValueError,
        match="No purchase price available",
    ):
        run_buy_and_hold_simulation(
            provider=provider,
            symbol="AAPL",
            asset_type="stock",
            initial_investment=Decimal("1000.00"),
            purchase_date=date(2026, 1, 2),
            valuation_date=date(2026, 1, 6),
        )


# Test 4: Invalid date order

def test_invalid_date_order():
    with pytest.raises(
        ValueError,
        match="Valuation date must be after purchase date",
    ):
        run_buy_and_hold_simulation(
            provider=sample_provider(),
            symbol="AAPL",
            asset_type="stock",
            initial_investment=Decimal("1000.00"),
            purchase_date=date(2026, 1, 6),
            valuation_date=date(2026, 1, 2),
        )


# Test 5: Selected purchase date after valuation

def test_purchase_after_available_valuation():
    with pytest.raises(
        ValueError,
        match="Purchase date is after available valuation date",
    ):
        run_buy_and_hold_simulation(
            provider=sample_provider(),
            symbol="AAPL",
            asset_type="stock",
            initial_investment=Decimal("1000.00"),
            purchase_date=date(2026, 1, 3),
            valuation_date=date(2026, 1, 4),
        )

@pytest.mark.parametrize("kind,works", [("stock", True), ("crypto", False)])
def test_market_specific_missing_date_gap(kind, works):
    provider = FakeHistoricalPriceProvider({"TEST": {
        date(2023, 1, 3): Decimal("100"), date(2023, 1, 6): Decimal("120"),
    }})
    if works:
        result = run_buy_and_hold_simulation(provider, "TEST", kind, Decimal("1000"), date(2023, 1, 1), date(2023, 1, 6))
        assert result.purchase_date == date(2023, 1, 3)
    else:
        with pytest.raises(ValueError, match="No purchase"):
            run_buy_and_hold_simulation(provider, "TEST", kind, Decimal("1000"), date(2023, 1, 1), date(2023, 1, 6))
