import os

import httpx
from dotenv import load_dotenv

from decimal import Decimal


load_dotenv()

ALPHA_VANTAGE_API_KEY = os.environ["ALPHA_VANTAGE_API_KEY"]

BASE_URL = "https://www.alphavantage.co/query"


def get_stock_quote(symbol: str) -> dict:
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()

    data = response.json()

    if "Note" in data or "Information" in data:
        raise RuntimeError(
            data.get("Note") or data.get("Information")
        )

    if "Error Message" in data:
        raise ValueError(data["Error Message"])

    quote = data.get("Global Quote")

    if not quote:
        raise RuntimeError(
            "Alpha Vantage returned no stock quote."
        )

    return {
        "symbol": quote["01. symbol"],
        "asset_type": "stock",
        "currency": "USD",
        "price": Decimal(quote["05. price"]),
        "as_of": quote["07. latest trading day"],
    }


def get_crypto_quote(symbol: str) -> dict:
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": symbol,
        "to_currency": "USD",
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.get(BASE_URL, params=params)
        response.raise_for_status()

    data = response.json()

    if "Note" in data or "Information" in data:
        raise RuntimeError(
            data.get("Note") or data.get("Information")
        )

    if "Error Message" in data:
        raise ValueError(data["Error Message"])

    exchange_rate = data.get("Realtime Currency Exchange Rate")

    if not exchange_rate:
        raise RuntimeError(
            "Alpha Vantage returned no cryptocurrency exchange rate."
        )

    return {
        "symbol": symbol,
        "asset_type": "crypto",
        "currency": "USD",
        "price": Decimal(exchange_rate["5. Exchange Rate"]),
        "as_of": exchange_rate.get("6. Last Refreshed"),
    }

def get_asset_quote(symbol: str, asset_type: str) -> dict:
    if asset_type == "stock":
        return get_stock_quote(symbol)

    if asset_type == "crypto":
        return get_crypto_quote(symbol)

    raise ValueError(f"Unsupported asset type: {asset_type}")