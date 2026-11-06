from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from datetime import date, datetime, timedelta, timezone

import httpx

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from larp_finance.models import Asset, Portfolio, Holding, Trade
from larp_finance.market_data import get_asset_quote
from larp_finance.schemas import TradeBuyRequest, TradeSellRequest


def fits_numeric(
    value: Decimal,
    precision: int,
    scale: int,
) -> bool:
    if not value.is_finite():
        return False

    max_value = Decimal(10) ** (precision - scale)

    return -max_value < value < max_value


def validate_quote_freshness(quote: dict) -> None:
    as_of = quote.get("as_of")
    asset_type = quote.get("asset_type")

    if not isinstance(as_of, str):
        raise ValueError("Missing quote timestamp")

    now = datetime.now(timezone.utc)

    if asset_type == "stock":
        try:
            trading_day = date.fromisoformat(as_of)
        except ValueError:
            raise ValueError("Invalid stock quote date")

        age = now.date() - trading_day

        if age.days < 0 or age.days > 5:
            raise ValueError("Stock quote is outdated")

    elif asset_type == "crypto":
        try:
            refreshed_at = datetime.fromisoformat(as_of)
        except ValueError:
            raise ValueError("Invalid crypto quote timestamp")

        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)

        age = now - refreshed_at

        if age < -timedelta(minutes=5):
            raise ValueError("Crypto quote is future-dated")

        if age > timedelta(hours=2):
            raise ValueError("Crypto quote is outdated")

    else:
        raise ValueError("Unsupported asset type")


def find_existing_trade(
    db: Session,
    portfolio_id: int,
    idempotency_key: str,
    trade_data: TradeBuyRequest | TradeSellRequest,
    trade_type: str = "buy",
) -> Trade | None:
    existing_trade = db.scalar(
        select(Trade).where(
            Trade.portfolio_id == portfolio_id,
            Trade.idempotency_key == idempotency_key,
        )
    )

    if existing_trade is None:
        return None

    if (
        existing_trade.trade_type != trade_type
        or existing_trade.asset_id != trade_data.asset_id
        or existing_trade.quantity != trade_data.quantity
    ):
        raise HTTPException(
            status_code=409,
            detail="Idempotency key already used for a different request",
        )

    return existing_trade


def execute_buy(
    trade_data: TradeBuyRequest,
    user_id: int,
    db: Session,
    idempotency_key: str | None = None,
) -> Trade:
    
    if idempotency_key is not None:
        existing_trade = db.scalar(
            select(Trade)
            .join(Portfolio, Trade.portfolio_id == Portfolio.id)
            .where(
                Portfolio.user_id == user_id,
                Trade.idempotency_key == idempotency_key,
            )
        )

        if existing_trade is not None:
            return find_existing_trade(
                db,
                existing_trade.portfolio_id,
                idempotency_key,
                trade_data,
            )

    # Step 1: Find the requested asset.
    asset = db.get(Asset, trade_data.asset_id)

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    # Step 2: Retrieve the market price.
    try:
        quote = get_asset_quote(asset.symbol, asset.asset_type)

        validate_quote_freshness(quote)
        
        unit_price = Decimal(str(quote["price"]))

        if quote["currency"] != "USD":
            raise ValueError("Unsupported quote currency")

        if not unit_price.is_finite() or unit_price <= 0:
            raise ValueError("Invalid market price")

        unit_price = unit_price.quantize(
            Decimal("0.00000001"),
            rounding=ROUND_HALF_UP,
        )

        if unit_price <= 0 or not fits_numeric(
            unit_price,
            precision=20,
            scale=8,
        ):
            raise ValueError("Invalid market price")

    except (
        RuntimeError,
        ValueError,
        KeyError,
        InvalidOperation,
        httpx.HTTPError,
    ):
        raise HTTPException(
            status_code=503,
            detail="Market data temporarily unavailable",
        )

    # Step 3: Calculate and validate the purchase cost.
    raw_total = trade_data.quantity * unit_price

    if raw_total < Decimal("1.00"):
        raise HTTPException(
            status_code=422,
            detail="Minimum purchase amount is $1.00",
        )

    total_amount = raw_total.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if not fits_numeric(
        total_amount,
        precision=28,
        scale=8,
    ):
        raise HTTPException(
            status_code=422,
            detail="Purchase amount exceeds supported limits",
        )

    # Step 4: Lock the user's portfolio.
    portfolio = db.scalar(
        select(Portfolio)
        .where(Portfolio.user_id == user_id)
        .with_for_update()
    )

    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )


    if idempotency_key is not None:
        existing_trade = find_existing_trade(
            db,
            portfolio.id,
            idempotency_key,
            trade_data,
        )

        if existing_trade is not None:
            return existing_trade



    # Step 5: Check available funds.
    if portfolio.cash_balance < total_amount:
        raise HTTPException(
            status_code=409,
            detail="Insufficient funds",
        )

    # Step 6: Find the existing holding.
    holding = db.scalar(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id,
            Holding.asset_id == asset.id,
        )
    )

    if holding is None:
        holding = Holding(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("0"),
            avg_cost=Decimal("0"),
        )
        db.add(holding)

    # Step 7: Calculate new holding values.
    old_quantity = holding.quantity
    new_quantity = old_quantity + trade_data.quantity

    if not fits_numeric(
        new_quantity,
        precision=28,
        scale=12,
    ):
        raise HTTPException(
            status_code=422,
            detail="Holding quantity exceeds supported limits",
        )

    new_avg_cost = (
        (
            old_quantity * holding.avg_cost
            + trade_data.quantity * unit_price
        ) / new_quantity
    ).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_HALF_UP,
    )

    if not fits_numeric(
        new_avg_cost,
        precision=20,
        scale=8,
    ):
        raise HTTPException(
            status_code=422,
            detail="Average cost exceeds supported limits",
        )

    holding.avg_cost = new_avg_cost
    holding.quantity = new_quantity

    # Step 8: Deduct cash.
    portfolio.cash_balance -= total_amount

    # Step 9: Record the purchase.
    new_trade = Trade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        trade_type="buy",
        quantity=trade_data.quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        idempotency_key=idempotency_key,
    )

    db.add(new_trade)

    # Step 10: Commit all changes atomically.
    try:
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Trade could not be completed",
        )

    db.refresh(new_trade)

    return new_trade


def execute_sell(
    trade_data: TradeSellRequest,
    user_id: int,
    db: Session,
    idempotency_key: str,
) -> Trade:

    if idempotency_key is not None:
        existing_trade = db.scalar(
            select(Trade)
            .join(Portfolio, Trade.portfolio_id == Portfolio.id)
            .where(
                Portfolio.user_id == user_id,
                Trade.idempotency_key == idempotency_key,
            )
        )

        if existing_trade is not None:
            return find_existing_trade(
                db,
                existing_trade.portfolio_id,
                idempotency_key,
                trade_data,
                trade_type="sell",
            )

    # Step 1: Find the asset.
    asset = db.get(Asset, trade_data.asset_id)

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    # Step 2: Retrieve and validate the market price.
    try:
        quote = get_asset_quote(asset.symbol, asset.asset_type)

        validate_quote_freshness(quote)

        unit_price = Decimal(str(quote["price"]))

        if quote["currency"] != "USD":
            raise ValueError("Unsupported quote currency")

        if not unit_price.is_finite() or unit_price <= 0:
            raise ValueError("Invalid market price")

        unit_price = unit_price.quantize(
            Decimal("0.00000001"),
            rounding=ROUND_HALF_UP,
        )

        if unit_price <= 0 or not fits_numeric(
            unit_price,
            precision=20,
            scale=8,
        ):
            raise ValueError("Invalid market price")

    except (
        RuntimeError,
        ValueError,
        KeyError,
        InvalidOperation,
        httpx.HTTPError,
    ):
        raise HTTPException(
            status_code=503,
            detail="Market data temporarily unavailable",
        )

    # Step 3: Calculate sale proceeds.
    raw_total = trade_data.quantity * unit_price

    if raw_total < Decimal("1.00"):
        raise HTTPException(
            status_code=422,
            detail="Minimum sale amount is $1.00",
        )

    total_amount = raw_total.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if not fits_numeric(
        total_amount,
        precision=28,
        scale=8,
    ):
        raise HTTPException(
            status_code=422,
            detail="Sale amount exceeds supported limits",
        )

    # Step 4: Lock the user's portfolio.
    portfolio = db.scalar(
        select(Portfolio)
        .where(Portfolio.user_id == user_id)
        .with_for_update()
    )

    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )

    if idempotency_key is not None:
        existing_trade = find_existing_trade(
            db,
            portfolio.id,
            idempotency_key,
            trade_data,
            trade_type="sell",
        )

        if existing_trade is not None:
            return existing_trade

    # Step 5: Verify available holdings.
    holding = db.scalar(
        select(Holding).where(
            Holding.portfolio_id == portfolio.id,
            Holding.asset_id == asset.id,
        )
    )

    if holding is None or holding.quantity < trade_data.quantity:
        raise HTTPException(
            status_code=409,
            detail="Insufficient holdings",
        )

    # Step 6: Reduce the holding.
    holding.quantity -= trade_data.quantity

    if holding.quantity == 0:
        holding.avg_cost = Decimal("0")

    # Step 7: Credit sale proceeds.
    new_cash_balance = portfolio.cash_balance + total_amount

    if not fits_numeric(
        new_cash_balance,
        precision=18,
        scale=2,
    ):
        raise HTTPException(
            status_code=422,
            detail="Cash balance exceeds supported limits",
        )

    portfolio.cash_balance = new_cash_balance

    # Step 8: Record the sale.
    new_trade = Trade(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        trade_type="sell",
        quantity=trade_data.quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        idempotency_key=idempotency_key,
    )

    db.add(new_trade)

    # Step 9: Commit the transaction.
    try:
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Trade could not be completed",
        )

    db.refresh(new_trade)

    return new_trade
