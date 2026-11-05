from decimal import Decimal

import pytest

from larp_finance import market_data


@pytest.fixture(autouse=True)
def clear_quote_cache():
    market_data.quote_cache.clear()
    yield
    market_data.quote_cache.clear()


def test_cache_miss_and_hit(monkeypatch):
    call_count = 0

    def fake_stock_quote(symbol):
        nonlocal call_count
        call_count += 1

        return {
            "symbol": symbol,
            "asset_type": "stock",
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": "2026-11-04",
        }

    monkeypatch.setattr(
        market_data,
        "get_stock_quote",
        fake_stock_quote,
    )

    first = market_data.get_asset_quote("AAPL", "stock")
    second = market_data.get_asset_quote("AAPL", "stock")

    assert first == second
    assert call_count == 1


def test_cache_expiration(monkeypatch):
    call_count = 0
    fake_time = 1000.0

    def fake_monotonic():
        return fake_time

    def fake_stock_quote(symbol):
        nonlocal call_count
        call_count += 1

        return {
            "symbol": symbol,
            "asset_type": "stock",
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": "2026-11-04",
        }

    monkeypatch.setattr(
        market_data,
        "monotonic",
        fake_monotonic,
    )

    monkeypatch.setattr(
        market_data,
        "get_stock_quote",
        fake_stock_quote,
    )

    market_data.get_asset_quote("AAPL", "stock")

    fake_time += market_data.CACHE_TTL_SECONDS + 1

    market_data.get_asset_quote("AAPL", "stock")

    assert call_count == 2


def test_separate_asset_cache_entries(monkeypatch):
    stock_calls = 0
    crypto_calls = 0

    def fake_stock_quote(symbol):
        nonlocal stock_calls
        stock_calls += 1

        return {
            "symbol": symbol,
            "asset_type": "stock",
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": "2026-11-04",
        }

    def fake_crypto_quote(symbol):
        nonlocal crypto_calls
        crypto_calls += 1

        return {
            "symbol": symbol,
            "asset_type": "crypto",
            "currency": "USD",
            "price": Decimal("80000.00"),
            "as_of": "2026-11-04",
        }

    monkeypatch.setattr(
        market_data,
        "get_stock_quote",
        fake_stock_quote,
    )

    monkeypatch.setattr(
        market_data,
        "get_crypto_quote",
        fake_crypto_quote,
    )

    market_data.get_asset_quote("AAPL", "stock")
    market_data.get_asset_quote("BTC", "crypto")

    market_data.get_asset_quote("AAPL", "stock")
    market_data.get_asset_quote("BTC", "crypto")

    assert stock_calls == 1
    assert crypto_calls == 1


def test_unsupported_asset_type():
    with pytest.raises(ValueError):
        market_data.get_asset_quote("AAPL", "banana")
