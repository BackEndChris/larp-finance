
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from larp_finance.database import get_db
from larp_finance.models import User
from larp_finance.schemas import TradeBuyRequest, TradeResponse
from larp_finance.auth import get_current_user
from larp_finance.services.trading import execute_buy


router = APIRouter()


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
