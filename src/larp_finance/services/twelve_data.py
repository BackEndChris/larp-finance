import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from zoneinfo import ZoneInfo

import httpx
from redis import Redis
from redis.exceptions import RedisError

from larp_finance.services.historical_cache import HistoricalPriceCache
from larp_finance.services.historical_errors import HistoricalPriceError, TemporaryHistoricalPriceError


STOCKS = {"AAPL", "MSFT", "NVDA", "TSLA"}
CRYPTO = {"BTC", "ETH", "SOL"}
BASE_URL = "https://api.twelvedata.com/time_series"
HTTP_TIMEOUT = httpx.Timeout(20, connect=5, pool=5, write=5)


@lru_cache(maxsize=4)
def redis_client(url):
    return Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)


def completed_day(asset_type):
    zone = ZoneInfo("America/New_York") if asset_type == "stock" else timezone.utc
    return datetime.now(zone).date() - timedelta(days=1)


class TwelveDataHistoricalPriceProvider:
    def __init__(self, api_key=None, *, cache=None, transport=None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY", "")
        if not self.api_key.strip():
            raise HistoricalPriceError("TWELVE_DATA_API_KEY is not configured")
        if cache is None:
            redis = redis_client(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            cache = HistoricalPriceCache(redis, self.api_key)
        self.cache = cache
        self.transport = transport

    def get_daily_closes(
        self, symbol: str, asset_type: str, start_date: date, end_date: date,
    ) -> dict[date, Decimal]:
        symbol = symbol.upper()
        if asset_type not in ("stock", "crypto") or symbol not in (STOCKS if asset_type == "stock" else CRYPTO):
            raise HistoricalPriceError("Unsupported historical asset")
        if start_date > end_date or (end_date - start_date).days > 4998:
            raise HistoricalPriceError("Invalid historical date range (maximum 4999 calendar days)")
        end_date = min(end_date, completed_day(asset_type))
        if start_date > end_date:
            raise HistoricalPriceError("No completed daily closes in requested range")
        # One response keeps both ends on the same split-adjustment basis.
        return self._window(symbol, asset_type, start_date, end_date)

    def _window(self, symbol, asset_type, start, end):
        key = self.cache.key(symbol, asset_type, start, end)
        try:
            cached = self.cache.get(key)
            if cached is not None:
                try:
                    return self._normalize_values(cached, start, end)
                except HistoricalPriceError:
                    self.cache.redis.delete(key)
            with self.cache.lock(key):
                cached = self.cache.get(key)
                if cached is not None:
                    return self._normalize_values(cached, start, end)
                self.cache.reserve_credit()
                values = self._request(symbol, asset_type, start, end)
                prices = self._normalize_values(values, start, end)
                self.cache.put(key, [dict(datetime=day.isoformat(), close=str(price))
                                     for day, price in prices.items()])
                return prices
        except RedisError:
            raise TemporaryHistoricalPriceError("Historical data cache temporarily unavailable") from None

    def _request(self, symbol, asset_type, start, end):
        provider_symbol = symbol if asset_type == "stock" else symbol + "/USD"
        params = dict(symbol=provider_symbol, interval="1day", start_date=start.isoformat(),
                      end_date=end.isoformat(), outputsize=5000, order="asc",
                      adjust="splits" if asset_type == "stock" else "none", format="JSON")
        if asset_type == "stock":
            params["exchange"] = "NASDAQ"
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, transport=self.transport, follow_redirects=False) as client:
                response = client.get(BASE_URL, params=params,
                                      headers={"Authorization": "apikey " + self.api_key})
        except httpx.RequestError:
            raise TemporaryHistoricalPriceError() from None
        code = response.status_code
        if code == 429:
            retry_after = response.headers.get("Retry-After", "300")
            delay = min(int(retry_after), 86400) if retry_after.isdigit() and len(retry_after) < 8 else 300
            self.cache.cooldown(delay)
            raise TemporaryHistoricalPriceError("Historical data provider rate limited", retry_after=delay)
        if code >= 500 or code == 408:
            raise TemporaryHistoricalPriceError()
        if code in (401, 403):
            raise HistoricalPriceError("Historical data provider authentication or entitlement failed")
        if code != 200:
            raise HistoricalPriceError("Historical data request rejected")
        try:
            data = json.loads(response.content, parse_float=Decimal)
        except (ValueError, UnicodeError):
            raise HistoricalPriceError("Malformed historical data response") from None
        if not isinstance(data, dict):
            raise HistoricalPriceError("Malformed historical data response")
        if data.get("status") == "error":
            code = str(data.get("code"))
            if code == "429" or code.startswith("5"):
                if code == "429":
                    self.cache.cooldown(300)
                raise TemporaryHistoricalPriceError("Historical data provider temporarily unavailable")
            if code in ("401", "403"):
                raise HistoricalPriceError("Historical data provider authentication or entitlement failed")
            raise HistoricalPriceError("Historical data unavailable for symbol or date range")
        meta = data.get("meta")
        if not isinstance(meta, dict) or (
            meta.get("symbol") != provider_symbol or meta.get("interval") != "1day"
            or (asset_type == "stock" and (meta.get("currency") != "USD" or meta.get("exchange_timezone") != "America/New_York"))
            or (asset_type == "crypto" and (meta.get("currency_quote") not in ("USD", "US Dollar") or meta.get("exchange_timezone") != "UTC"))
        ):
            raise HistoricalPriceError("Unexpected historical data instrument, currency or timezone")
        if data.get("status") != "ok":
            raise HistoricalPriceError("Malformed historical data response")
        return data.get("values")

    @staticmethod
    def _normalize_values(values, start, end):
        if not isinstance(values, list) or len(values) > 5000:
            raise HistoricalPriceError("Malformed historical prices")
        prices = {}
        try:
            for row in values:
                day_text = row["datetime"]
                day = date.fromisoformat(day_text)
                if day.isoformat() != day_text:
                    raise ValueError()
                raw = row["close"]
                if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
                    raise ValueError()
                price = Decimal(raw)
                if not price.is_finite() or price <= 0 or price >= Decimal("1e12") or price < Decimal("0.00000001"):
                    raise ValueError()
                if day in prices:
                    raise ValueError()
                if start <= day <= end:
                    prices[day] = price
        except (ValueError, TypeError, KeyError, InvalidOperation):
            raise HistoricalPriceError("Invalid historical date or closing price") from None
        return prices
