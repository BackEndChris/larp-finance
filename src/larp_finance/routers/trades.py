
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from larp_finance.database import get_db
from larp_finance.models import User, Portfolio, Trade
from larp_finance.schemas import TradeBuyRequest, TradeSellRequest, TradeResponse
from larp_finance.auth import get_current_user
from larp_finance.services.trading import execute_buy, execute_sell


router = APIRouter(tags=["Trades"])


@router.post(
    "/trades/buy",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
def buy_asset(
    trade_data: TradeBuyRequest,
    idempotency_key: str = Header(
        min_length=1,
        max_length=64,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return execute_buy(
        trade_data=trade_data,
        user_id=current_user.id,
        db=db,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/trades/sell",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
)
def sell_asset(
    trade_data: TradeSellRequest,
    idempotency_key: str = Header(
        min_length=1,
        max_length=64,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return execute_sell(
        trade_data=trade_data,
        user_id=current_user.id,
        db=db,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/trades",
    response_model=list[TradeResponse],
)
def get_trade_history(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    trades = db.scalars(
        select(Trade)
        .join(Portfolio, Trade.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == current_user.id)
        .order_by(Trade.created_at.desc(), Trade.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return trades
