import os

import httpx
from dotenv import load_dotenv

from decimal import Decimal, InvalidOperation
from time import monotonic
from threading import Lock


load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

BASE_URL = "https://www.alphavantage.co/query"

CACHE_TTL_SECONDS = 3600

quote_cache = {}
cache_lock = Lock()


def response_data(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("Malformed market data response") from None
    if not isinstance(data, dict):
        raise RuntimeError("Malformed market data response")
    if "Note" in data or "Information" in data or "Error Message" in data:
        raise RuntimeError("Market data request rejected by provider")
    return data


def positive_price(raw) -> Decimal:
    try:
        price = Decimal(str(raw))
    except InvalidOperation:
        raise RuntimeError("Invalid market price") from None
    if not price.is_finite() or price <= 0:
        raise RuntimeError("Invalid market price")
    return price


def get_stock_quote(symbol: str) -> dict:

    if not ALPHA_VANTAGE_API_KEY:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")
    
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()

    data = response_data(response)

    quote = data.get("Global Quote")

    if not isinstance(quote, dict):
        raise RuntimeError(
            "Alpha Vantage returned no stock quote."
        )

    if quote.get("01. symbol") != symbol or not isinstance(quote.get("07. latest trading day"), str):
        raise RuntimeError("Incomplete market data response")

    return {
        "symbol": quote["01. symbol"],
        "asset_type": "stock",
        "currency": "USD",
        "price": positive_price(quote.get("05. price")),
        "as_of": quote["07. latest trading day"],
    }


def get_crypto_quote(symbol: str) -> dict:
    if not ALPHA_VANTAGE_API_KEY:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": symbol,
        "to_currency": "USD",
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()

    data = response_data(response)

    exchange_rate = data.get("Realtime Currency Exchange Rate")

    if not isinstance(exchange_rate, dict):
        raise RuntimeError(
            "Alpha Vantage returned no cryptocurrency exchange rate."
        )

    if exchange_rate.get("6. Last Refreshed") is not None and not isinstance(exchange_rate["6. Last Refreshed"], str):
        raise RuntimeError("Invalid market data timestamp")

    return {
        "symbol": symbol,
        "asset_type": "crypto",
        "currency": "USD",
        "price": positive_price(exchange_rate.get("5. Exchange Rate")),
        "as_of": exchange_rate.get("6. Last Refreshed"),
    }


def get_asset_quote(symbol: str, asset_type: str) -> dict:
    symbol = symbol.upper()
    asset_type = asset_type.lower()

    if asset_type not in ("stock", "crypto"):
        raise ValueError(f"Unsupported asset type: {asset_type}")

    cache_key = (symbol, asset_type)

    with cache_lock:
        current_time = monotonic()

        cached_entry = quote_cache.get(cache_key)

        if cached_entry is not None:
            quote, expires_at = cached_entry

            if current_time < expires_at:
                return quote.copy()

        if asset_type == "stock":
            quote = get_stock_quote(symbol)
        else:
            quote = get_crypto_quote(symbol)

        quote_cache[cache_key] = (
            quote.copy(),
            monotonic() + CACHE_TTL_SECONDS,
        )

        return quote.copy()
