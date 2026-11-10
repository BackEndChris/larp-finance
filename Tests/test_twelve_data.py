from contextlib import nullcontext
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from larp_finance import tasks
from larp_finance.services import twelve_data
from larp_finance.services.historical_cache import HistoricalPriceCache
from larp_finance.services.historical_errors import HistoricalPriceError, TemporaryHistoricalPriceError
from larp_finance.services.simulation_service import run_buy_and_hold_simulation


START, END = date(2020, 8, 28), date(2020, 8, 31)


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.credits = 0
        self.cooldown = Mock()
        self.redis = Mock()

    def key(self, *args):
        return args

    def get(self, key):
        return self.values.get(key)

    def put(self, key, values):
        self.values[key] = values

    def reserve_credit(self):
        self.credits += 1

    def lock(self, key):
        return nullcontext()


def payload(symbol="AAPL", asset_type="stock", values=None):
    meta = dict(symbol=symbol, interval="1day")
    if asset_type == "stock":
        meta.update(currency="USD", exchange_timezone="America/New_York")
    else:
        meta.update(currency_base="Bitcoin", currency_quote="US Dollar", exchange_timezone="UTC")
    return dict(status="ok", meta=meta, values=values if values is not None else [
        {"datetime": "2020-08-28", "close": "124.8075"},
        {"datetime": "2020-08-31", "close": "129.04"},
    ])


def provider_for(handler, cache=None):
    return twelve_data.TwelveDataHistoricalPriceProvider(
        api_key="test-secret", cache=cache or MemoryCache(), transport=httpx.MockTransport(handler),
    )


def test_split_adjusted_stock_request_and_cache():
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.params["adjust"] == "splits"
        assert request.url.params["exchange"] == "NASDAQ"
        assert request.url.params["interval"] == "1day"
        assert request.headers["Authorization"] == "apikey test-secret"
        assert "test-secret" not in str(request.url)
        assert request.extensions["timeout"]["connect"] == 5
        assert request.extensions["timeout"]["read"] == 20
        return httpx.Response(200, json=payload())
    cache = MemoryCache()
    provider = provider_for(respond, cache)
    result = run_buy_and_hold_simulation(provider, "AAPL", "stock", Decimal("1000"), START, END)
    # Apple's 4:1 split occurred on 2020-08-31; both prices use split-adjusted units.
    assert result.purchase_price == Decimal("124.8075")
    assert result.profit_loss == Decimal("33.91")
    provider.get_daily_closes("aapl", "stock", START - timedelta(days=7), END + timedelta(days=7))
    assert len(requests) == cache.credits == 1


@pytest.mark.parametrize("symbol", ["BTC", "ETH", "SOL"])
def test_crypto_uses_usd_and_raw_daily_closes(symbol):
    def respond(request):
        assert request.url.params["symbol"] == symbol + "/USD"
        assert request.url.params["adjust"] == "none"
        return httpx.Response(200, json=payload(symbol + "/USD", "crypto"))
    prices = provider_for(respond).get_daily_closes(symbol, "crypto", START, END)
    assert prices[START] == Decimal("124.8075")


@pytest.mark.parametrize("status", [401, 403, 404, 422, 302])
def test_rejected_http_responses_are_safe_permanent_errors(status):
    provider = provider_for(lambda request: httpx.Response(status, text="test-secret"))
    with pytest.raises(HistoricalPriceError) as exc:
        provider.get_daily_closes("AAPL", "stock", START, END)
    assert not isinstance(exc.value, TemporaryHistoricalPriceError)
    assert "test-secret" not in str(exc.value)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_http_responses(status):
    provider = provider_for(lambda request: httpx.Response(status, headers={"Retry-After": "120"}))
    with pytest.raises(TemporaryHistoricalPriceError) as exc:
        provider.get_daily_closes("AAPL", "stock", START, END)
    if status == 429:
        assert exc.value.retry_after == 120
        provider.cache.cooldown.assert_called_once_with(120)
    assert not provider.cache.values


@pytest.mark.parametrize("code,temporary", [(401, False), (403, False), (400, False), (429, True), (500, True)])
def test_provider_errors_in_successful_http_response(code, temporary):
    provider = provider_for(lambda request: httpx.Response(200, json={"status": "error", "code": code, "message": "test-secret"}))
    with pytest.raises(HistoricalPriceError) as exc:
        provider.get_daily_closes("AAPL", "stock", START, END)
    assert isinstance(exc.value, TemporaryHistoricalPriceError) == temporary
    assert "test-secret" not in str(exc.value)


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "NaN", "Infinity", True, {}, "1e1000000", "1e-1000000"])
def test_unusable_prices_are_rejected(raw):
    provider = provider_for(lambda request: httpx.Response(200, json=payload(values=[{"datetime": str(START), "close": raw}])))
    with pytest.raises(HistoricalPriceError, match="Invalid historical"):
        provider.get_daily_closes("AAPL", "stock", START, END)


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null", b'{"status":"ok"}', b'{"meta":{},"values":[]}'])
def test_malformed_responses(body):
    provider = provider_for(lambda request: httpx.Response(200, content=body))
    with pytest.raises(HistoricalPriceError):
        provider.get_daily_closes("AAPL", "stock", START, END)


def test_mismatched_instrument_metadata():
    data = payload()
    data["meta"]["currency"] = "EUR"
    provider = provider_for(lambda request: httpx.Response(200, json=data))
    with pytest.raises(HistoricalPriceError, match="Unexpected"):
        provider.get_daily_closes("AAPL", "stock", START, END)


def test_duplicate_dates_are_rejected():
    row = {"datetime": str(START), "close": "100"}
    provider = provider_for(lambda request: httpx.Response(200, json=payload(values=[row, row])))
    with pytest.raises(HistoricalPriceError):
        provider.get_daily_closes("AAPL", "stock", START, END)


def test_missing_observations_are_not_filled():
    provider = provider_for(lambda request: httpx.Response(200, json=payload(values=[])))
    assert provider.get_daily_closes("AAPL", "stock", START, END) == {}
    with pytest.raises(ValueError, match="No purchase"):
        run_buy_and_hold_simulation(provider, "AAPL", "stock", Decimal("1000"), START, END)


@pytest.mark.parametrize("symbol,kind,start,end", [
    ("UNKNOWN", "stock", START, END), ("BTC", "bond", START, END),
    ("AAPL", "stock", END, START), ("AAPL", "stock", date(1990, 1, 1), END),
])
def test_invalid_asset_or_range_never_requests(symbol, kind, start, end):
    handler = Mock()
    with pytest.raises(HistoricalPriceError):
        provider_for(handler).get_daily_closes(symbol, kind, start, end)
    handler.assert_not_called()


def test_unfinished_and_future_days_are_excluded(monkeypatch):
    monkeypatch.setattr(twelve_data, "completed_day", lambda kind: START)
    def respond(request):
        assert request.url.params["end_date"] == str(START)
        return httpx.Response(200, json=payload())
    assert provider_for(respond).get_daily_closes("AAPL", "stock", START, END) == {START: Decimal("124.8075")}


def test_network_error_is_retryable_and_safe():
    def timeout(request):
        raise httpx.ReadTimeout("test-secret", request=request)
    with pytest.raises(TemporaryHistoricalPriceError) as exc:
        provider_for(timeout).get_daily_closes("AAPL", "stock", START, END)
    assert "test-secret" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_cache_failure_does_not_bypass_quota():
    cache = MemoryCache()
    cache.get = Mock(side_effect=RedisConnectionError("offline"))
    handler = Mock()
    with pytest.raises(TemporaryHistoricalPriceError, match="cache"):
        provider_for(handler, cache).get_daily_closes("AAPL", "stock", START, END)
    handler.assert_not_called()


def test_real_provider_selection_and_missing_configuration(monkeypatch):
    monkeypatch.setenv("LARP_SIMULATION_MODE", "real")
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    assert tasks.configured_data_source() == "twelve_data"
    with pytest.raises(HistoricalPriceError, match="not configured"):
        tasks.build_simulation_provider(symbol="AAPL", purchase_date=START, valuation_date=END)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-secret")
    assert isinstance(tasks.build_simulation_provider(symbol="AAPL", purchase_date=START, valuation_date=END), twelve_data.TwelveDataHistoricalPriceProvider)
    # An existing real job cannot become fictional after changing the default mode.
    monkeypatch.setenv("LARP_SIMULATION_MODE", "demo")
    assert isinstance(tasks.build_simulation_provider(symbol="AAPL", purchase_date=START, valuation_date=END, data_source="twelve_data"), twelve_data.TwelveDataHistoricalPriceProvider)


def test_cache_namespaces_and_daily_quota():
    redis = Mock()
    cache = HistoricalPriceCache(redis, "test-secret")
    assert "test-secret" not in cache.key("AAPL", "stock", START, END)
    assert cache.key("AAPL", "stock", START, END) != HistoricalPriceCache(redis, "another-account").key("AAPL", "stock", START, END)
    redis.eval.return_value = -1
    with pytest.raises(TemporaryHistoricalPriceError) as exc:
        cache.reserve_credit()
    assert exc.value.retry_after == 86400
    redis.eval.return_value = 0
    redis.ttl.return_value = 120
    with pytest.raises(TemporaryHistoricalPriceError) as exc:
        cache.reserve_credit()
    assert exc.value.retry_after == 120


def test_completed_day_uses_market_timezone(monkeypatch):
    from datetime import datetime, timezone
    instant = datetime(2026, 1, 3, 0, 30, tzinfo=timezone.utc)
    class FrozenDatetime:
        @classmethod
        def now(cls, zone):
            return instant.astimezone(zone)
    monkeypatch.setattr(twelve_data, "datetime", FrozenDatetime)
    assert twelve_data.completed_day("stock") == date(2026, 1, 1)
    assert twelve_data.completed_day("crypto") == date(2026, 1, 2)


def test_numeric_json_prices_preserve_decimal_precision():
    body = b'{"status":"ok","meta":{"symbol":"AAPL","interval":"1day","currency":"USD","exchange_timezone":"America/New_York"},"values":[{"datetime":"2020-08-28","close":124.807500001}]}'
    provider = provider_for(lambda request: httpx.Response(200, content=body))
    assert provider.get_daily_closes("AAPL", "stock", START, END)[START] == Decimal("124.807500001")
