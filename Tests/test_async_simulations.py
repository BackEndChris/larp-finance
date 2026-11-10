from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from kombu.exceptions import OperationalError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError as DatabaseError
from sqlalchemy.orm import Session

from larp_finance import tasks
from larp_finance.models import Asset, Simulation, User
from larp_finance.services import simulation_dispatch as dispatch
from larp_finance.services import simulation_processing as processing


@pytest.fixture
def simulation(db_session):
    key = uuid4().hex[:10]
    user = User(username=key, email=f"{key}@example.com", password_hash="test")
    asset = Asset(symbol=key.upper(), name="Test", asset_type="stock")
    db_session.add_all([user, asset])
    db_session.flush()
    row = Simulation(user_id=user.id, asset_id=asset.id,
                     initial_investment=Decimal("1000"),
                     purchase_date=date(2023, 1, 2), valuation_date=date(2024, 1, 2))
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def publish(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(tasks.process_simulation_task, "apply_async", mock)
    return mock


def test_publication_failure_recovers(db_session, simulation, publish):
    publish.side_effect = OperationalError("offline")
    dispatch.dispatch_simulations(db_session, simulation.id)
    db_session.refresh(simulation)
    assert simulation.status == "pending"
    assert simulation.dispatch_attempts == 1
    assert simulation.next_dispatch_at > datetime.now(timezone.utc)
    publish.side_effect = None
    simulation.next_dispatch_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    dispatch.dispatch_simulations(db_session, simulation.id)
    assert publish.call_count == 2
    db_session.refresh(simulation)
    assert simulation.dispatch_attempts == 2


@pytest.mark.parametrize("status,attempts", [("pending", 0), ("running", 0), ("running", 3)])
def test_recovery_is_bounded(db_session, simulation, publish, status, attempts):
    simulation.status = status
    simulation.processing_token = "abandoned"
    simulation.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    simulation.processing_attempts = attempts
    simulation.dispatch_attempts = 12 if status == "pending" else 0
    db_session.commit()
    dispatch.dispatch_simulations(db_session, simulation.id)
    db_session.refresh(simulation)
    assert simulation.status == ("pending" if status == "running" and attempts == 0 else "failed")
    assert simulation.processing_token is None
    assert publish.call_count == (1 if simulation.status == "pending" else 0)


@pytest.mark.parametrize("expire,fail", [(True, False), (True, True), (False, True)])
def test_late_and_stale_workers_cannot_write(db_session, simulation, expire, fail):
    simulation_id = simulation.id
    class Provider:
        def get_daily_closes(self, **kwargs):
            changes = {"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)} if expire else {"processing_token": "replacement"}
            db_session.execute(update(Simulation).where(Simulation.id == simulation_id).values(**changes))
            db_session.commit()
            if fail:
                raise ValueError("calculation failed")
            return {simulation.purchase_date: Decimal("100"), simulation.valuation_date: Decimal("120")}
    if fail:
        with pytest.raises(ValueError):
            processing.process_simulation(db_session, simulation_id, Provider())
    else:
        processing.process_simulation(db_session, simulation_id, Provider())
    db_session.refresh(simulation)
    assert simulation.status == "running"
    assert simulation.final_value is None
    assert simulation.error_message is None


@pytest.mark.parametrize("committed", [False, True])
def test_result_commit_failure_is_recoverable(db_session, simulation, monkeypatch, committed):
    provider = tasks.build_simulation_provider(symbol="TEST", purchase_date=simulation.purchase_date,
                                             valuation_date=simulation.valuation_date)
    asset = db_session.get(Asset, simulation.asset_id)
    provider.prices[asset.symbol] = provider.prices.pop("TEST")
    real_commit = db_session.commit
    calls = 0
    def commit():
        nonlocal calls
        calls += 1
        if calls == 2:
            if committed:
                real_commit()
            raise DatabaseError("commit", {}, Exception("offline"))
        real_commit()
    monkeypatch.setattr(db_session, "commit", commit)
    with pytest.raises(DatabaseError):
        processing.process_simulation(db_session, simulation.id, provider)
    db_session.refresh(simulation)
    assert simulation.status == ("completed" if committed else "running")
    assert simulation.final_value == (Decimal("1200") if committed else None)
    assert (simulation.processing_token is None) == committed


def test_task_owns_and_closes_session(test_engine, monkeypatch):
    sessions = []
    def session_factory():
        db = Session(test_engine)
        sessions.append(db)
        return db
    process = Mock()
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(tasks, "process_simulation", process)
    tasks.process_simulation_task.run(123)
    assert len(sessions) == 1
    process.assert_called_once_with(sessions[0], 123, provider_factory=tasks.build_simulation_provider)
    assert not sessions[0].in_transaction()


def test_demo_mode_must_be_explicit(monkeypatch):
    monkeypatch.delenv("LARP_SIMULATION_MODE", raising=False)
    with pytest.raises(ValueError, match="explicit demo"):
        tasks.build_simulation_provider(symbol="TEST", purchase_date=date(2023, 1, 1), valuation_date=date(2024, 1, 1))


def test_concurrent_claim_and_reclaim(test_engine, monkeypatch):
    key = uuid4().hex[:10]
    with Session(test_engine) as db:
        user = User(username=key, email=f"{key}@example.com", password_hash="test")
        asset = Asset(symbol=key.upper(), name="Test", asset_type="stock")
        db.add_all([user, asset])
        db.flush()
        row = Simulation(user_id=user.id, asset_id=asset.id, initial_investment=Decimal("1000"),
                         purchase_date=date(2023, 1, 2), valuation_date=date(2024, 1, 2))
        db.add(row)
        db.commit()
        simulation_id, user_id, asset_id = row.id, user.id, asset.id
    started, release = Event(), Event()
    barrier = Barrier(2)
    calls = []
    class SlowProvider:
        def get_daily_closes(self, **kwargs):
            calls.append(1)
            started.set()
            assert release.wait(15)
            return {date(2023, 1, 2): Decimal("100"), date(2024, 1, 2): Decimal("999")}
    def run():
        with Session(test_engine) as db:
            barrier.wait(15)
            processing.process_simulation(db, simulation_id, SlowProvider())
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run) for _ in range(2)]
            assert started.wait(15)
            done, _ = wait(futures, timeout=15, return_when=FIRST_COMPLETED)
            assert len(done) == 1
            # While retrieval is blocked, another session can lock and reclaim the row.
            with Session(test_engine) as db:
                row = db.scalar(select(Simulation).where(Simulation.id == simulation_id).with_for_update(nowait=True))
                assert row.status == "running"
                assert row.processing_attempts == 1
                row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
            with Session(test_engine) as db:
                processing.process_simulation(db, simulation_id, provider_factory=tasks.build_simulation_provider)
            release.set()
            for future in futures:
                future.result(timeout=15)
        assert len(calls) == 1
        with Session(test_engine) as db:
            row = db.get(Simulation, simulation_id)
            assert row.status == "completed"
            assert row.final_value == Decimal("1200")
            assert row.processing_attempts == 2
            processing.process_simulation(db, simulation_id, SlowProvider())
            assert db.get(Simulation, simulation_id).final_value == Decimal("1200")
    finally:
        release.set()
        with Session(test_engine) as db:
            db.execute(delete(Simulation).where(Simulation.id == simulation_id))
            db.execute(delete(User).where(User.id == user_id))
            db.execute(delete(Asset).where(Asset.id == asset_id))
            db.commit()

@pytest.fixture
def durable_simulation(test_engine):
    key = uuid4().hex[:10]
    with Session(test_engine) as db:
        user = User(username=key, email=f"{key}@example.com", password_hash="test")
        asset = Asset(symbol=key.upper(), name="Test", asset_type="stock")
        db.add_all([user, asset])
        db.flush()
        row = Simulation(user_id=user.id, asset_id=asset.id,
                         initial_investment=Decimal("1000"), purchase_date=date(2023, 1, 2),
                         valuation_date=date(2024, 1, 2))
        db.add(row)
        db.commit()
        ids = row.id, user.id, asset.id
    try:
        yield ids
    finally:
        with Session(test_engine) as db:
            db.execute(delete(Simulation).where(Simulation.user_id == ids[1]))
            db.execute(delete(User).where(User.id == ids[1]))
            db.execute(delete(Asset).where(Asset.id == ids[2]))
            db.commit()


@pytest.mark.parametrize("offline", [False, True])
def test_api_commits_before_publishing(test_engine, durable_simulation, monkeypatch, offline):
    from fastapi.testclient import TestClient
    from larp_finance.auth import get_current_user
    from larp_finance.database import get_db
    from larp_finance.main import app

    _, user_id, asset_id = durable_simulation
    published = []
    def publish(*, args, retry):
        assert retry is False
        with Session(test_engine) as other:
            row = other.get(Simulation, args[0])
            assert row is not None
            assert row.user_id == user_id
            published.append(row.id)
        if offline:
            raise OperationalError("offline")
    monkeypatch.setattr(tasks.process_simulation_task, "apply_async", publish)
    with Session(test_engine) as db:
        user = db.get(User, user_id)
        def get_session():
            with Session(test_engine) as request_db:
                yield request_db
        app.dependency_overrides[get_db] = get_session
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            with TestClient(app) as client:
                response = client.post("/simulations", json={
                    "asset_id": asset_id, "initial_investment": "1000.00",
                    "purchase_date": "2023-01-02", "valuation_date": "2024-01-02",
                })
            assert response.status_code == 201
            assert response.json()["status"] == "pending"
            assert published == [response.json()["id"]]
            with Session(test_engine) as other:
                row = other.get(Simulation, published[0])
                assert row.dispatch_attempts == 1
                assert row.status == "pending"
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


def test_concurrent_dispatch_skips_locked_row(test_engine, durable_simulation, monkeypatch):
    simulation_id = durable_simulation[0]
    published, release = Event(), Event()
    calls = []
    def publish(**kwargs):
        calls.append(kwargs)
        published.set()
        assert release.wait(15)
    monkeypatch.setattr(tasks.process_simulation_task, "apply_async", publish)
    def scan():
        with Session(test_engine) as db:
            return dispatch.dispatch_simulations(db, simulation_id)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(scan)
        try:
            assert published.wait(15)
            assert executor.submit(scan).result(timeout=15) == 0
        finally:
            release.set()
        assert first.result(timeout=15) == 1
    assert len(calls) == 1


def test_task_redelivery_uses_new_sessions(test_engine, durable_simulation, monkeypatch):
    sessions = []
    def factory():
        db = Session(test_engine)
        sessions.append(db)
        return db
    monkeypatch.setattr(tasks, "SessionLocal", factory)
    for _ in range(2):
        tasks.process_simulation_task.run(durable_simulation[0])
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert all(not db.in_transaction() for db in sessions)
    with Session(test_engine) as db:
        row = db.get(Simulation, durable_simulation[0])
        assert row.status == "completed"
        assert row.processing_attempts == 1
        assert row.final_value == Decimal("1200")


def test_claim_commit_failure_does_not_claim(db_session, simulation, monkeypatch):
    simulation_id = simulation.id
    def fail():
        raise DatabaseError("commit", {}, Exception("offline"))
    monkeypatch.setattr(db_session, "commit", fail)
    with pytest.raises(DatabaseError):
        processing.process_simulation(db_session, simulation_id, provider_factory=tasks.build_simulation_provider)
    db_session.refresh(simulation)
    assert simulation.status == "pending"
    assert simulation.processing_attempts == 0
    assert simulation.processing_token is None


def test_persisted_demo_source_survives_configuration_change(db_session, simulation, monkeypatch):
    monkeypatch.delenv("LARP_SIMULATION_MODE")
    processing.process_simulation(db_session, simulation.id, provider_factory=tasks.build_simulation_provider)
    db_session.refresh(simulation)
    assert simulation.status == "completed"
    assert simulation.data_source == "demo"
    assert simulation.processing_token is None
    assert simulation.lease_expires_at is None


def test_completed_job_is_never_dispatched(db_session, simulation, publish):
    processing.process_simulation(db_session, simulation.id, provider_factory=tasks.build_simulation_provider)
    simulation_id = simulation.id
    dispatch.dispatch_simulations(db_session, simulation_id)
    publish.assert_not_called()
    db_session.refresh(simulation)
    assert simulation.status == "completed"
    assert simulation.final_value == Decimal("1200")

@pytest.mark.parametrize("status", [429, 503, 401])
def test_real_provider_errors_follow_durable_retry_policy(db_session, simulation, monkeypatch, status):
    from contextlib import nullcontext
    import httpx
    from larp_finance.services.twelve_data import TwelveDataHistoricalPriceProvider
    from larp_finance.services.historical_errors import HistoricalPriceError, TemporaryHistoricalPriceError

    simulation.data_source = "twelve_data"
    db_session.get(Asset, simulation.asset_id).symbol = "AAPL"
    simulation_id = simulation.id
    db_session.commit()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status)
    cache = Mock()
    cache.get.return_value = None
    cache.lock.side_effect = lambda key: nullcontext()
    provider = TwelveDataHistoricalPriceProvider("test-secret", cache=cache, transport=httpx.MockTransport(respond))
    with pytest.raises(HistoricalPriceError):
        processing.process_simulation(db_session, simulation_id, provider)
    db_session.refresh(simulation)
    assert simulation.status == ("failed" if status == 401 else "pending")
    assert simulation.processing_token is None
    if status != 401:
        assert simulation.retry_not_before > datetime.now(timezone.utc)
        processing.process_simulation(db_session, simulation_id, provider)
        assert len(calls) == 1
        for attempt in range(2):
            simulation.retry_not_before = datetime.now(timezone.utc) - timedelta(seconds=1)
            simulation.next_dispatch_at = simulation.retry_not_before
            db_session.commit()
            with pytest.raises(TemporaryHistoricalPriceError):
                processing.process_simulation(db_session, simulation_id, provider)
            db_session.refresh(simulation)
        assert simulation.status == "failed"
        assert simulation.processing_attempts == 3
        assert len(calls) == 3


def test_real_task_persists_source_and_actual_dates(test_engine, durable_simulation, monkeypatch):
    from contextlib import nullcontext
    import httpx
    from larp_finance.services.twelve_data import TwelveDataHistoricalPriceProvider

    simulation_id = durable_simulation[0]
    with Session(test_engine) as db:
        simulation = db.get(Simulation, simulation_id)
        simulation.data_source = "twelve_data"
        simulation.purchase_date = date(2023, 1, 1)
        db.get(Asset, simulation.asset_id).symbol = "AAPL"
        db.commit()
    cache = Mock()
    cache.get.return_value = None
    cache.lock.side_effect = lambda key: nullcontext()
    data = {"status": "ok", "meta": {"symbol": "AAPL", "interval": "1day", "currency": "USD", "exchange_timezone": "America/New_York"},
            "values": [{"datetime": "2023-01-03", "close": "125"}, {"datetime": "2024-01-02", "close": "200"}]}
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=data)
    provider = TwelveDataHistoricalPriceProvider("test-secret", cache=cache, transport=httpx.MockTransport(respond))
    monkeypatch.setattr(tasks, "TwelveDataHistoricalPriceProvider", lambda: provider)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: Session(test_engine))
    tasks.process_simulation_task.run(simulation_id)
    tasks.process_simulation_task.run(simulation_id)
    with Session(test_engine) as db:
        simulation = db.get(Simulation, simulation_id)
        assert simulation.data_source == "twelve_data"
        assert simulation.purchase_date == date(2023, 1, 1)
        assert simulation.actual_purchase_date == date(2023, 1, 3)
        assert simulation.actual_valuation_date == date(2024, 1, 2)
        assert simulation.final_value == Decimal("1600")
        assert simulation.profit_loss == Decimal("600")
    assert len(calls) == 1
