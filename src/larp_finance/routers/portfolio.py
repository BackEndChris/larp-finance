from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from larp_finance.database import get_db
from larp_finance.models import User, Portfolio
from larp_finance.schemas import PortfolioResponse
from larp_finance.auth import get_current_user


router = APIRouter(tags=["Portfolio"])


@router.get(
    "/portfolio/me",
    response_model=PortfolioResponse,
)
def get_my_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    portfolio = db.scalar(
        select(Portfolio).where(
            Portfolio.user_id == current_user.id
        )
    )

    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )

    return portfolio
