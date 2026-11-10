from decimal import Decimal

import pytest

from larp_finance.services.simulation_engine import (
    calculate_buy_and_hold,
)


# Test 1: Profitable investment

def test_profitable_investment():
    result = calculate_buy_and_hold(
        Decimal("1000.00"),
        Decimal("50.00"),
        Decimal("80.00"),
    )

    assert result["quantity"] == Decimal("20")
    assert result["final_value"] == Decimal("1600.00")
    assert result["profit_loss"] == Decimal("600.00")


# Test 2: Investment loses value

def test_losing_investment():
    result = calculate_buy_and_hold(
        Decimal("1000.00"),
        Decimal("50.00"),
        Decimal("25.00"),
    )

    assert result["final_value"] == Decimal("500.00")
    assert result["profit_loss"] == Decimal("-500.00")


# Test 3: Fractional shares are supported

def test_fractional_shares():
    result = calculate_buy_and_hold(
        Decimal("100.00"),
        Decimal("300.00"),
        Decimal("600.00"),
    )

    assert result["final_value"] == Decimal("200.00")
    assert result["profit_loss"] == Decimal("100.00")


# Test 4: Invalid prices are rejected

@pytest.mark.parametrize(
    "price",
    [
        Decimal("0"),
        Decimal("-10"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_purchase_price(price):
    with pytest.raises(ValueError):
        calculate_buy_and_hold(
            Decimal("1000.00"),
            price,
            Decimal("80.00"),
        )


# Test 5: Investment below minimum is rejected

def test_investment_below_minimum():
    with pytest.raises(ValueError):
        calculate_buy_and_hold(
            Decimal("0.50"),
            Decimal("50.00"),
            Decimal("80.00"),
        )
