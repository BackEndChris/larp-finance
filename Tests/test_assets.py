from decimal import Decimal

import pytest

from larp_finance.models import Asset
from larp_finance import main


@pytest.fixture
def sample_asset(db_session):
    asset = Asset(
        symbol="AAPL",
        name="Apple Inc.",
        asset_type="stock",
    )

    db_session.add(asset)
    db_session.flush()

    return asset


def test_list_assets(client, sample_asset):
    response = client.get("/assets")

    assert response.status_code == 200

    assets = response.json()

    assert len(assets) == 1
    assert assets[0]["symbol"] == "AAPL"
    assert assets[0]["asset_type"] == "stock"


def test_get_asset_quote(client, sample_asset, monkeypatch):
    def fake_quote(symbol, asset_type):
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": "2026-11-04",
        }

    monkeypatch.setattr(main, "get_asset_quote", fake_quote)

    response = client.get("/assets/AAPL/quote")

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
    assert Decimal(response.json()["price"]) == Decimal("200.00")


def test_unknown_asset_returns_404(client):
    response = client.get("/assets/NOTREAL/quote")

    assert response.status_code == 404


def test_market_data_failure_returns_503(
    client,
    sample_asset,
    monkeypatch,
):
    def fake_quote(symbol, asset_type):
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(main, "get_asset_quote", fake_quote)

    response = client.get("/assets/AAPL/quote")

    assert response.status_code == 503
