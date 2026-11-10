from datetime import date
from decimal import Decimal

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
