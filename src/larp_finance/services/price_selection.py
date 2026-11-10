from datetime import date, timedelta
from decimal import Decimal


MAX_DATE_GAP = timedelta(days=7)


def select_purchase_price(
    prices: dict[date, Decimal],
    requested_date: date,
) -> tuple[date, Decimal]:
    candidates = [
        day
        for day in prices
        if requested_date <= day <= requested_date + MAX_DATE_GAP
    ]

    if not candidates:
        raise ValueError("No purchase price available")

    selected_date = min(candidates)
    price = prices[selected_date]

    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid purchase price")

    return selected_date, price


def select_valuation_price(
    prices: dict[date, Decimal],
    valuation_date: date,
) -> tuple[date, Decimal]:
    candidates = [
        day
        for day in prices
        if valuation_date - MAX_DATE_GAP <= day <= valuation_date
    ]

    if not candidates:
        raise ValueError("No valuation price available")

    selected_date = max(candidates)
    price = prices[selected_date]

    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid valuation price")

    return selected_date, price
