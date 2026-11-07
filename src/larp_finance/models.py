from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, String, func, ForeignKey, Numeric, CheckConstraint, UniqueConstraint, Date
from sqlalchemy.orm import Mapped, mapped_column


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


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"),
        nullable=False,
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
    )

    trade_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(28, 12),
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(28, 8),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "trade_type IN ('buy', 'sell')",
            name="ck_trade_type",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_trade_quantity",
        ),
        CheckConstraint(
            "unit_price > 0",
            name="ck_trade_unit_price",
        ),
        CheckConstraint(
            "total_amount > 0",
            name="ck_trade_total_amount",
        ),
        UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="uq_trade_portfolio_idempotency_key",
        ),
    )

class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
    )

    initial_investment: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
    )

    purchase_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    purchase_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    final_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    final_value: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 2),
        nullable=True,
    )

    profit_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 2),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "initial_investment >= 1",
            name="ck_simulation_minimum_investment",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_simulation_status",
        ),
    )
