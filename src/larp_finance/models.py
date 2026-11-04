from datetime import datetime

from sqlalchemy import DateTime, String, func, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from larp_finance.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )

    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("10000.00"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
