from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from sqlalchemy import update

from larp_finance.models import Asset, Simulation, User
from larp_finance.services.fake_market_data import (
    FakeHistoricalPriceProvider,
)
from larp_finance.services.simulation_processing import (
    process_simulation,
)


def test_process_simulation_success(db_session):
    # Create an asset.
    asset = Asset(
        symbol="TESTSTOCK",
        name="Test Stock",
        asset_type="stock",
    )

    db_session.add(asset)
    db_session.flush()

    # Create a user.
    user = User(
        username="ProcessingTester",
        email="processingtester@example.com",
        password_hash="test-hash",
    )

    db_session.add(user)
    db_session.flush()

    # Create a pending simulation.
    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        status="pending",
    )

    db_session.add(simulation)
    db_session.flush()

    # Capture the ID before processing.
    simulation_id = simulation.id

    # Supply deterministic historical prices.
    provider = FakeHistoricalPriceProvider(
        prices={
            "TESTSTOCK": {
                date(2026, 1, 2): Decimal("100.00"),
                date(2026, 1, 6): Decimal("120.00"),
            }
        }
    )

    process_simulation(
        db=db_session,
        simulation_id=simulation_id,
        provider=provider,
    )

    db_session.refresh(simulation)

    assert simulation.status == "completed"
    assert simulation.purchase_price == Decimal("100.00")
    assert simulation.final_price == Decimal("120.00")
    assert simulation.final_value == Decimal("1200.00")
    assert simulation.profit_loss == Decimal("200.00")
    assert simulation.error_message is None


def test_completed_simulation_is_not_processed_again(db_session):
    # Create the required asset.
    asset = Asset(
        symbol="DUPTEST",
        name="Duplicate Test Stock",
        asset_type="stock",
    )
    db_session.add(asset)
    db_session.flush()

    # Create the required user.
    user = User(
        username="DuplicateTester",
        email="duplicatetester@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    # Create an already completed simulation.
    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        purchase_price=Decimal("100.00"),
        final_price=Decimal("120.00"),
        final_value=Decimal("1200.00"),
        profit_loss=Decimal("200.00"),
        status="completed",
    )
    db_session.add(simulation)
    db_session.flush()

    simulation_id = simulation.id

    db_session.commit()
    
    # Empty provider: recalculating would fail.
    provider = FakeHistoricalPriceProvider(prices={})

    process_simulation(
        db=db_session,
        simulation_id=simulation_id,
        provider=provider,
    )

    db_session.refresh(simulation)

    assert simulation.status == "completed"
    assert simulation.final_value == Decimal("1200.00")
    assert simulation.profit_loss == Decimal("200.00")
    assert simulation.error_message is None

def test_process_simulation_failure(db_session):
    # Test 3: Failed Simulation

    asset = Asset(
        symbol="FAILTEST",
        name="Failure Test Stock",
        asset_type="stock",
    )
    db_session.add(asset)
    db_session.flush()

    user = User(
        username="FailureTester",
        email="failuretester@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        status="pending",
    )
    db_session.add(simulation)
    db_session.flush()

    simulation_id = simulation.id

    class FailingProvider:
        def get_daily_closes(
            self,
            symbol,
            asset_type,
            start_date,
            end_date,
        ):
            raise RuntimeError("Market data unavailable")

    with pytest.raises(
        RuntimeError,
        match="Market data unavailable",
    ):
        process_simulation(
            db=db_session,
            simulation_id=simulation_id,
            provider=FailingProvider(),
        )

    db_session.refresh(simulation)

    assert simulation.status == "failed"
    assert simulation.error_message == (
        "RuntimeError: Simulation processing failed"
    )
    assert simulation.purchase_price is None
    assert simulation.final_value is None
    assert simulation.profit_loss is None


def test_expired_simulation_lease(db_session):
    # Test 4: Expired Lease Recovery

    asset = Asset(
        symbol="LEASETEST",
        name="Lease Test Stock",
        asset_type="stock",
    )
    db_session.add(asset)
    db_session.flush()

    user = User(
        username="LeaseTester",
        email="leasetester@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        status="running",
        processing_token="old-worker-token",
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    db_session.add(simulation)
    db_session.flush()

    provider = FakeHistoricalPriceProvider(
        prices={
            "LEASETEST": {
                date(2026, 1, 2): Decimal("100.00"),
                date(2026, 1, 6): Decimal("120.00"),
            }
        }
    )

    process_simulation(
        db=db_session,
        simulation_id=simulation.id,
        provider=provider,
    )

    db_session.refresh(simulation)

    assert simulation.status == "completed"
    assert simulation.final_value == Decimal("1200.00")
    assert simulation.profit_loss == Decimal("200.00")
    assert simulation.processing_token is None
    assert simulation.lease_expires_at is None



def test_active_simulation_lease(db_session):
    # Test 5: Active Lease Protection

    asset = Asset(
        symbol="ACTIVELEASE",
        name="Active Lease Stock",
        asset_type="stock",
    )
    db_session.add(asset)
    db_session.flush()

    user = User(
        username="ActiveLeaseTester",
        email="activelease@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        status="running",
        processing_token="active-worker-token",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db_session.add(simulation)
    db_session.flush()

    simulation_id = simulation.id
    db_session.commit()

    provider = FakeHistoricalPriceProvider(prices={})

    process_simulation(
        db=db_session,
        simulation_id=simulation_id,
        provider=provider,
    )

    db_session.refresh(simulation)

    assert simulation.status == "running"
    assert simulation.processing_token == "active-worker-token"
    assert simulation.final_value is None
    assert simulation.profit_loss is None


def test_simulation_loses_ownership(db_session):
    # Test 6: Lost Worker Ownership

    asset = Asset(
        symbol="OWNERSHIP",
        name="Ownership Test Stock",
        asset_type="stock",
    )
    db_session.add(asset)
    db_session.flush()

    user = User(
        username="OwnershipTester",
        email="ownershiptester@example.com",
        password_hash="test-hash",
    )
    db_session.add(user)
    db_session.flush()

    simulation = Simulation(
        user_id=user.id,
        asset_id=asset.id,
        initial_investment=Decimal("1000.00"),
        purchase_date=date(2026, 1, 2),
        valuation_date=date(2026, 1, 6),
        status="pending",
    )
    db_session.add(simulation)
    db_session.flush()

    simulation_id = simulation.id
    db_session.commit()

    class OwnershipChangingProvider(FakeHistoricalPriceProvider):
        def get_daily_closes(
            self,
            symbol,
            asset_type,
            start_date,
            end_date,
        ):
            db_session.execute(
                update(Simulation)
                .where(Simulation.id == simulation_id)
                .values(processing_token="replacement-worker-token")
            )
            db_session.commit()

            return super().get_daily_closes(
                symbol,
                asset_type,
                start_date,
                end_date,
            )

    provider = OwnershipChangingProvider(
        prices={
            "OWNERSHIP": {
                date(2026, 1, 2): Decimal("100.00"),
                date(2026, 1, 6): Decimal("120.00"),
            }
        }
    )

    process_simulation(
        db=db_session,
        simulation_id=simulation_id,
        provider=provider,
    )

    db_session.refresh(simulation)

    assert simulation.status == "running"
    assert simulation.processing_token == "replacement-worker-token"
    assert simulation.final_value is None
    assert simulation.profit_loss is None
