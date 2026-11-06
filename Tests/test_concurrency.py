from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from larp_finance.models import User, Portfolio, Asset, Holding, Trade
from larp_finance.schemas import TradeBuyRequest, TradeSellRequest
from larp_finance.services import trading


# Test 1: Concurrent Purchases

def test_concurrent_buys_cannot_overspend(test_engine, monkeypatch):
    unique_id = uuid4().hex[:10]
    barrier = Barrier(2)

    with Session(test_engine) as db:
        user = User(
            username=f"Concurrent{unique_id}",
            email=f"concurrent{unique_id}@example.com",
            password_hash="test-only",
        )

        stock = Asset(
            symbol=f"TST{unique_id}",
            name="Test Stock",
            asset_type="stock",
        )

        crypto = Asset(
            symbol=f"CRY{unique_id}",
            name="Test Crypto",
            asset_type="crypto",
        )

        db.add_all([user, stock, crypto])
        db.flush()

        portfolio = Portfolio(user_id=user.id)
        db.add(portfolio)
        db.flush()

        user_id = user.id
        portfolio_id = portfolio.id
        stock_id = stock.id
        crypto_id = crypto.id
        stock_symbol = stock.symbol
        crypto_symbol = crypto.symbol

        db.commit()

    def fake_quote(symbol, asset_type):
        barrier.wait(timeout=15)

        price = (
            Decimal("7000.00")
            if symbol == stock_symbol
            else Decimal("6000.00")
        )

        as_of = (
            datetime.now(timezone.utc).date().isoformat()
            if asset_type == "stock"
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": price,
            "as_of": as_of,
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    def attempt_purchase(asset_id):
        with Session(test_engine) as db:
            try:
                trade = trading.execute_buy(
                    trade_data=TradeBuyRequest(
                        asset_id=asset_id,
                        quantity=Decimal("1"),
                    ),
                    user_id=user_id,
                    db=db,
                    idempotency_key=f"concurrent-{asset_id}",
                )

                return ("success", trade.total_amount)

            except HTTPException as exc:
                return ("rejected", exc.status_code)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(attempt_purchase, stock_id)
            second = executor.submit(attempt_purchase, crypto_id)

            results = [
                first.result(),
                second.result(),
            ]

        assert sum(
            result[0] == "success" for result in results
        ) == 1

        assert ("rejected", 409) in results

        with Session(test_engine) as db:
            portfolio = db.get(Portfolio, portfolio_id)

            holdings = db.scalars(
                select(Holding).where(
                    Holding.portfolio_id == portfolio_id
                )
            ).all()

            trades = db.scalars(
                select(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            ).all()

            assert len(holdings) == 1
            assert len(trades) == 1

            spent = trades[0].total_amount

            assert spent in (
                Decimal("6000.00"),
                Decimal("7000.00"),
            )

            assert portfolio.cash_balance == (
                Decimal("10000.00") - spent
            )

            assert portfolio.cash_balance >= 0

    finally:
        with Session(test_engine) as db:
            db.execute(
                delete(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Holding).where(
                    Holding.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Portfolio).where(
                    Portfolio.id == portfolio_id
                )
            )

            db.execute(
                delete(User).where(
                    User.id == user_id
                )
            )

            db.execute(
                delete(Asset).where(
                    Asset.id.in_([stock_id, crypto_id])
                )
            )

            db.commit()


# Test 2: Concurrent Idempotent Purchases

def test_concurrent_idempotent_buys(test_engine, monkeypatch):
    unique_id = uuid4().hex[:10]
    barrier = Barrier(2)

    with Session(test_engine) as db:
        user = User(
            username=f"Idem{unique_id}",
            email=f"idem{unique_id}@example.com",
            password_hash="test-only",
        )

        asset = Asset(
            symbol=f"IDM{unique_id}",
            name="Idempotency Test Stock",
            asset_type="stock",
        )

        db.add_all([user, asset])
        db.flush()

        portfolio = Portfolio(user_id=user.id)
        db.add(portfolio)
        db.flush()

        user_id = user.id
        asset_id = asset.id
        portfolio_id = portfolio.id

        db.commit()

    def fake_quote(symbol, asset_type):
        barrier.wait(timeout=15)

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

    def attempt_purchase():
        with Session(test_engine) as db:
            trade = trading.execute_buy(
                trade_data=TradeBuyRequest(
                    asset_id=asset_id,
                    quantity=Decimal("3"),
                ),
                user_id=user_id,
                db=db,
                idempotency_key="concurrent-buy-001",
            )

            return trade.id

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(attempt_purchase)
            second = executor.submit(attempt_purchase)

            results = [
                first.result(),
                second.result(),
            ]

        assert results[0] == results[1]

        with Session(test_engine) as db:
            portfolio = db.get(Portfolio, portfolio_id)

            holdings = db.scalars(
                select(Holding).where(
                    Holding.portfolio_id == portfolio_id
                )
            ).all()

            trades = db.scalars(
                select(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            ).all()

            assert portfolio.cash_balance == Decimal("9400.00")

            assert len(holdings) == 1
            assert holdings[0].quantity == Decimal("3")

            assert len(trades) == 1
            assert trades[0].idempotency_key == "concurrent-buy-001"

    finally:
        with Session(test_engine) as db:
            db.execute(
                delete(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Holding).where(
                    Holding.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Portfolio).where(
                    Portfolio.id == portfolio_id
                )
            )

            db.execute(
                delete(User).where(
                    User.id == user_id
                )
            )

            db.execute(
                delete(Asset).where(
                    Asset.id == asset_id
                )
            )

            db.commit()


# Test 3: Concurrent Overselling

def test_concurrent_sells_cannot_oversell(test_engine, monkeypatch):
    unique_id = uuid4().hex[:10]
    barrier = Barrier(2)

    with Session(test_engine) as db:
        user = User(
            username=f"Seller{unique_id}",
            email=f"seller{unique_id}@example.com",
            password_hash="test-only",
        )

        asset = Asset(
            symbol=f"SEL{unique_id}",
            name="Concurrent Sale Test",
            asset_type="stock",
        )

        db.add_all([user, asset])
        db.flush()

        portfolio = Portfolio(user_id=user.id)
        db.add(portfolio)
        db.flush()

        holding = Holding(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("3"),
            avg_cost=Decimal("200.00"),
        )

        portfolio.cash_balance = Decimal("9400.00")

        db.add(holding)

        user_id = user.id
        asset_id = asset.id
        portfolio_id = portfolio.id

        db.commit()

    def fake_quote(symbol, asset_type):
        barrier.wait(timeout=15)

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "currency": "USD",
            "price": Decimal("250.00"),
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }

    monkeypatch.setattr(
        trading,
        "get_asset_quote",
        fake_quote,
    )

    def attempt_sale(key):
        with Session(test_engine) as db:
            try:
                trade = trading.execute_sell(
                    trade_data=TradeSellRequest(
                        asset_id=asset_id,
                        quantity=Decimal("2"),
                    ),
                    user_id=user_id,
                    db=db,
                    idempotency_key=key,
                )

                return ("success", trade.id)

            except HTTPException as exc:
                return ("rejected", exc.status_code)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                attempt_sale,
                "concurrent-sale-001",
            )

            second = executor.submit(
                attempt_sale,
                "concurrent-sale-002",
            )

            results = [
                first.result(),
                second.result(),
            ]

        assert sum(
            result[0] == "success" for result in results
        ) == 1

        assert ("rejected", 409) in results

        with Session(test_engine) as db:
            portfolio = db.get(Portfolio, portfolio_id)

            holding = db.scalar(
                select(Holding).where(
                    Holding.portfolio_id == portfolio_id,
                    Holding.asset_id == asset_id,
                )
            )

            trades = db.scalars(
                select(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            ).all()

            assert portfolio.cash_balance == Decimal("9900.00")

            assert holding.quantity == Decimal("1")
            assert holding.avg_cost == Decimal("200.00")

            assert len(trades) == 1
            assert trades[0].trade_type == "sell"
            assert trades[0].quantity == Decimal("2")
            assert trades[0].total_amount == Decimal("500.00")

    finally:
        with Session(test_engine) as db:
            db.execute(
                delete(Trade).where(
                    Trade.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Holding).where(
                    Holding.portfolio_id == portfolio_id
                )
            )

            db.execute(
                delete(Portfolio).where(
                    Portfolio.id == portfolio_id
                )
            )

            db.execute(
                delete(User).where(
                    User.id == user_id
                )
            )

            db.execute(
                delete(Asset).where(
                    Asset.id == asset_id
                )
            )

            db.commit()
