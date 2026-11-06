from pydantic import BaseModel, EmailStr, Field
from decimal import Decimal
from datetime import datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    username: str
    password: str


class PortfolioResponse(BaseModel):
    id: int
    user_id: int
    cash_balance: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}

class AssetResponse(BaseModel):
    id: int
    symbol: str
    name: str
    asset_type: str

    model_config = {"from_attributes": True}

class AssetQuoteResponse(BaseModel):
    symbol: str
    asset_type: str
    currency: str
    price: Decimal
    as_of: str | None

class TradeBuyRequest(BaseModel):
    asset_id: int = Field(gt=0)
    quantity: Decimal = Field(
        gt=0,
        max_digits=28,
        decimal_places=12,
    )

class TradeResponse(BaseModel):
    id: int
    portfolio_id: int
    asset_id: int
    trade_type: str
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}

class TradeSellRequest(BaseModel):
    asset_id: int = Field(gt=0)
    quantity: Decimal = Field(
        gt=0,
        max_digits=28,
        decimal_places=12,
    )
