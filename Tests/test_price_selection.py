from datetime import date
from decimal import Decimal

import pytest

from larp_finance.services.price_selection import (
    select_purchase_price,
    select_valuation_price,
)


def sample_prices():
    return {
        date(2026, 1, 2): Decimal("100.00"),
        date(2026, 1, 5): Decimal("105.00"),
        date(2026, 1, 6): Decimal("110.00"),
    }


# Test 1: Purchase on a trading day

def test_purchase_on_trading_day():
    selected_date, price = select_purchase_price(
        sample_prices(),
        date(2026, 1, 2),
    )

    assert selected_date == date(2026, 1, 2)
    assert price == Decimal("100.00")


# Test 2: Purchase during a weekend

def test_purchase_on_weekend():
    selected_date, price = select_purchase_price(
        sample_prices(),
        date(2026, 1, 3),
    )

    assert selected_date == date(2026, 1, 5)
    assert price == Decimal("105.00")


# Test 3: Valuation during a weekend

def test_valuation_on_weekend():
    selected_date, price = select_valuation_price(
        sample_prices(),
        date(2026, 1, 3),
    )

    assert selected_date == date(2026, 1, 2)
    assert price == Decimal("100.00")


# Test 4: Missing purchase data

def test_missing_purchase_price():
    with pytest.raises(
        ValueError,
        match="No purchase price available",
    ):
        select_purchase_price(
            sample_prices(),
            date(2025, 1, 1),
        )


# Test 5: Missing valuation data

def test_missing_valuation_price():
    with pytest.raises(
        ValueError,
        match="No valuation price available",
    ):
        select_valuation_price(
            sample_prices(),
            date(2026, 2, 1),
        )


# Test 6: Invalid price

def test_invalid_purchase_price():
    prices = {
        date(2026, 1, 5): Decimal("-10.00"),
    }

    with pytest.raises(
        ValueError,
        match="Invalid purchase price",
    ):
        select_purchase_price(
            prices,
            date(2026, 1, 5),
        )
