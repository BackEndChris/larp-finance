from datetime import datetime

from sqlalchemy import DateTime, String, func, ForeignKey, Numeric, CheckConstraint, UniqueConstraint
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


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    asset_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "asset_type",
            name="uq_asset_symbol_type",
        ),
        CheckConstraint(
            "asset_type IN ('stock', 'crypto')",
            name="ck_asset_type",
        ),
    )


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"),
        nullable=False,
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(28, 12),
        nullable=False,
    )

    avg_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "asset_id",
            name="uq_portfolio_asset",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="ck_holding_quantity",
        ),
        CheckConstraint(
            "avg_cost >= 0",
            name="ck_holding_avg_cost",
        ),
    )
