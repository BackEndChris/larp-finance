from decimal import Decimal

from sqlalchemy import select, event

from larp_finance.models import Asset, Holding, Portfolio, Trade
from larp_finance.services import trading

from datetime import datetime, timedelta, timezone


def register_and_login(client, username, email):
    registration = client.post(
        "/register",
        json={
            "username": username,
            "email": email,
            "password": "SecurePassword123!",
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/login",
        json={
            "username": username,
            "password": "SecurePassword123!",
        },
    )

    assert login.status_code == 200

    headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "Idempotency-Key": f"test-{username}",
    }

    return registration.json()["id"], headers


def create_test_asset(db_session, symbol="AAPL"):
    asset = Asset(
        symbol=symbol,
        name="Apple Inc." if symbol == "AAPL" else "Bitcoin",
        asset_type="stock" if symbol == "AAPL" else "crypto",
    )

    db_session.add(asset)
    db_session.flush()

    return asset



def mock_market_price(monkeypatch, price):
    def fake_quote(symbol, asset_type):
        now = datetime.now(timezone.utc)

        as_of = (
            now.date().isoformat()
            if asset_type == "stock"
            else now.isoformat()
        )

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal(str(price)),
            "as_of": as_of,
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )




def get_test_portfolio(db_session, user_id):
    portfolio = db_session.scalar(
        select(Portfolio).where(
            Portfolio.user_id == user_id
        )
    )

    assert portfolio is not None
    db_session.refresh(portfolio)

    return portfolio


def assert_no_purchase(db_session, portfolio):
    holdings = db_session.scalars(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id
        )
    ).all()

    trades = db_session.scalars(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id
        )
    ).all()

    assert portfolio.cash_balance == Decimal("10000.00")
    assert len(holdings) == 0
    assert len(trades) == 0


# Test 1: Successful Purchase

def test_buy_asset_success(client, db_session, monkeypatch):
    user_id, headers = register_and_login(
        client,
        "TradeTester",
        "tradetester@example.com",
    )

    asset = create_test_asset(db_session)

    mock_market_price(monkeypatch, "200.00")

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "3",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text

    trade_data = response.json()

    assert trade_data["trade_type"] == "buy"
    assert Decimal(trade_data["quantity"]) == Decimal("3")
    assert Decimal(trade_data["unit_price"]) == Decimal("200")
    assert Decimal(trade_data["total_amount"]) == Decimal("600")

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("9400.00")

    holding = db_session.scalar(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id,
            Holding.asset_id == asset.id,
        )
    )

    assert holding is not None
    assert holding.quantity == Decimal("3")
    assert holding.avg_cost == Decimal("200")

    trade = db_session.get(Trade, trade_data["id"])

    assert trade is not None
    assert trade.trade_type == "buy"


# Test 2: Insufficient Funds

def test_buy_insufficient_funds(client, db_session, monkeypatch):
    user_id, headers = register_and_login(
        client,
        "BrokeInvestor",
        "broke@example.com",
    )

    asset = create_test_asset(db_session)

    mock_market_price(monkeypatch, "200.00")

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "60",
        },
        headers=headers,
    )

    assert response.status_code == 409

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)


# Test 3: Buying the Same Asset Twice

def test_buy_same_asset_twice(client, db_session, monkeypatch):
    user_id, headers = register_and_login(
        client,
        "RepeatInvestor",
        "repeat@example.com",
    )

    asset = create_test_asset(db_session)

    current_price = Decimal("200.00")

    def fake_quote(symbol, asset_type):
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": current_price,
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    first = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "2",
        },
        headers=headers,
    )

    assert first.status_code == 201, first.text

    headers["Idempotency-Key"] = "test-repeat-investor-second-buy"

    current_price = Decimal("250.00")

    second = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "3",
        },
        headers=headers,
    )

    assert second.status_code == 201, second.text

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("8850.00")

    holdings = db_session.scalars(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id,
            Holding.asset_id == asset.id,
        )
    ).all()

    assert len(holdings) == 1

    holding = holdings[0]
    db_session.refresh(holding)

    assert holding.quantity == Decimal("5")
    assert holding.avg_cost == Decimal("230.00")

    trades = db_session.scalars(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id
        ).order_by(Trade.id)
    ).all()

    assert len(trades) == 2
    assert trades[0].total_amount == Decimal("400.00")
    assert trades[1].total_amount == Decimal("750.00")


# Test 4: Database Rollback

def test_buy_rollback_on_database_error(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "RollbackTester",
        "rollback@example.com",
    )

    asset = create_test_asset(db_session)

    mock_market_price(monkeypatch, "200.00")

    def corrupt_trade(mapper, connection, target):
        target.trade_type = "invalid"

    event.listen(Trade, "before_insert", corrupt_trade)

    try:
        response = client.post(
            "/trades/buy",
            json={
                "asset_id": asset.id,
                "quantity": "3",
            },
            headers=headers,
        )
    finally:
        event.remove(Trade, "before_insert", corrupt_trade)

    assert response.status_code == 500

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)


# Test 5: Purchase Below $1 Minimum

def test_buy_rejects_zero_cent_purchase(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "TinyInvestor",
        "tiny@example.com",
    )

    asset = create_test_asset(db_session, symbol="BTC")

    mock_market_price(monkeypatch, "80000.00")

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "0.00000001",
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Minimum purchase amount is $1.00"
    )

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)


# Test 6: Outdated Crypto Quote

def test_buy_rejects_stale_crypto_quote(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "StaleInvestor",
        "stale@example.com",
    )

    asset = create_test_asset(db_session, symbol="BTC")

    def fake_quote(symbol, asset_type):
        old_timestamp = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        )

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("80000.00"),
            "as_of": old_timestamp.isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "0.01",
        },
        headers=headers,
    )

    assert response.status_code == 503

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)

# Test 7: Recent Stock Quote

def test_buy_accepts_recent_stock_quote(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "RecentStockInvestor",
        "recentstock@example.com",
    )

    asset = create_test_asset(db_session, symbol="AAPL")

    def fake_quote(symbol, asset_type):
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "3",
        },
        headers=headers,
    )

    assert response.status_code == 201, response.text

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("9400.00")

    holdings = db_session.scalars(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id
        )
    ).all()

    assert len(holdings) == 1
    assert holdings[0].quantity == Decimal("3")


# Test 8: Outdated Stock Quote

def test_buy_rejects_stale_stock_quote(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "StaleStockInvestor",
        "stalestock@example.com",
    )

    asset = create_test_asset(db_session, symbol="AAPL")

    def fake_quote(symbol, asset_type):
        old_date = (
            datetime.now(timezone.utc).date()
            - timedelta(days=10)
        )

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": old_date.isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "3",
        },
        headers=headers,
    )

    assert response.status_code == 503

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)


# Test 9: Idempotent Purchase Retry

def test_buy_idempotent_retry(client, db_session, monkeypatch):
    user_id, headers = register_and_login(
        client,
        "RetryInvestor",
        "retry@example.com",
    )

    asset = create_test_asset(db_session)
    headers["Idempotency-Key"] = "test-retry-001"

    quote_calls = 0

    def fake_quote(symbol, asset_type):
        nonlocal quote_calls
        quote_calls += 1

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("200.00"),
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    purchase = {
        "asset_id": asset.id,
        "quantity": "3",
    }

    first = client.post(
        "/trades/buy",
        json=purchase,
        headers=headers,
    )

    second = client.post(
        "/trades/buy",
        json=purchase,
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    assert first.json() == second.json()
    assert quote_calls == 1

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("9400.00")

    holdings = db_session.scalars(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id
        )
    ).all()

    trades = db_session.scalars(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id
        )
    ).all()

    assert len(holdings) == 1
    assert holdings[0].quantity == Decimal("3")

    assert len(trades) == 1
    assert trades[0].idempotency_key == "test-retry-001"


# Test 10: Same Key With Different Quantity

def test_buy_idempotency_quantity_conflict(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "QuantityInvestor",
        "quantity@example.com",
    )

    asset = create_test_asset(db_session)
    headers["Idempotency-Key"] = "test-quantity-001"

    mock_market_price(monkeypatch, "200.00")

    first = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "2",
        },
        headers=headers,
    )

    second = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "5",
        },
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409

    assert second.json()["detail"] == (
        "Idempotency key already used for a different request"
    )

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("9600.00")

    trades = db_session.scalars(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id
        )
    ).all()

    assert len(trades) == 1
    assert trades[0].quantity == Decimal("2")


# Test 11: Same Key With Different Asset

def test_buy_idempotency_asset_conflict(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "AssetConflictInvestor",
        "assetconflict@example.com",
    )

    stock = create_test_asset(db_session, symbol="AAPL")
    crypto = create_test_asset(db_session, symbol="BTC")

    headers["Idempotency-Key"] = "test-asset-001"

    mock_market_price(monkeypatch, "200.00")

    first = client.post(
        "/trades/buy",
        json={
            "asset_id": stock.id,
            "quantity": "2",
        },
        headers=headers,
    )

    second = client.post(
        "/trades/buy",
        json={
            "asset_id": crypto.id,
            "quantity": "2",
        },
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409

    portfolio = get_test_portfolio(db_session, user_id)

    assert portfolio.cash_balance == Decimal("9600.00")

    trades = db_session.scalars(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id
        )
    ).all()

    assert len(trades) == 1
    assert trades[0].asset_id == stock.id


# Test 12: Missing Idempotency Key

def test_buy_requires_idempotency_key(
    client,
    db_session,
    monkeypatch,
):
    user_id, headers = register_and_login(
        client,
        "MissingKeyInvestor",
        "missingkey@example.com",
    )

    asset = create_test_asset(db_session)

    headers.pop("Idempotency-Key")

    def unexpected_quote(symbol, asset_type):
        raise AssertionError("Market quote should not be requested")

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        unexpected_quote,
    )

    response = client.post(
        "/trades/buy",
        json={
            "asset_id": asset.id,
            "quantity": "3",
        },
        headers=headers,
    )

    assert response.status_code == 422

    portfolio = get_test_portfolio(db_session, user_id)

    assert_no_purchase(db_session, portfolio)
