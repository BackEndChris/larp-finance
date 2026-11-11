import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from larp_finance.database import get_db
from larp_finance.models import Asset
from larp_finance.schemas import AssetResponse, AssetQuoteResponse
from larp_finance.market_data import get_asset_quote


router = APIRouter(tags=["Assets"])


@router.get(
    "/assets",
    response_model=list[AssetResponse],
)
def list_assets(
    db: Session = Depends(get_db),
):
    assets = db.scalars(
        select(Asset).order_by(Asset.symbol)
    ).all()

    return assets


@router.get(
    "/assets/{symbol}/quote",
    response_model=AssetQuoteResponse,
)
def get_quote(
    symbol: str,
    db: Session = Depends(get_db),
):
    symbol = symbol.upper()

    asset = db.scalar(
        select(Asset).where(Asset.symbol == symbol)
    )

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail="Asset not found",
        )

    try:
        quote = get_asset_quote(
            asset.symbol,
            asset.asset_type,
        )

    except (RuntimeError, httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Market data temporarily unavailable",
        )

    return quote
