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