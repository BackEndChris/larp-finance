from pydantic import BaseModel, EmailStr, Field
from decimal import Decimal
from datetime import date, datetime


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

class SimulationCreate(BaseModel):
    asset_id: int = Field(gt=0)
    initial_investment: Decimal = Field(
        ge=Decimal("1.00"),
        max_digits=20,
        decimal_places=2,
    )
    purchase_date: date
    valuation_date: date


class SimulationResponse(BaseModel):
    id: int
    user_id: int
    asset_id: int
    initial_investment: Decimal
    purchase_date: date
    valuation_date: date
    status: str
    data_source: str
    actual_purchase_date: date | None
    actual_valuation_date: date | None

    purchase_price: Decimal | None
    final_price: Decimal | None
    final_value: Decimal | None
    profit_loss: Decimal | None
    error_message: str | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
