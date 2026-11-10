"""Pipe into `docker compose --env-file .env.docker exec -T worker python -`."""
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
from kombu.exceptions import OperationalError
from sqlalchemy import delete, select

from larp_finance.database import SessionLocal
from larp_finance.models import Asset, Portfolio, Simulation, User
from larp_finance.services.simulation_dispatch import dispatch_simulations
from larp_finance.tasks import process_simulation_task

key = "Verify" + uuid4().hex[:12]
user_id = None
failure_worker = None


def await_status(simulation_id, expected):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            row = db.get(Simulation, simulation_id)
            if row.status == expected:
                if expected == "completed":
                    assert row.final_value == Decimal("1200")
                assert row.processing_token is None
                assert row.lease_expires_at is None
                return
        time.sleep(0.1)
    raise AssertionError(f"Simulation did not reach {expected}")


try:
    with httpx.Client(base_url="http://api:8000", timeout=10) as client:
        assert client.get("/").status_code == 200
        password = uuid4().hex + "Aa1!"
        response = client.post("/register", json={"username": key, "email": key + "@example.com", "password": password})
        assert response.status_code == 201, response.status_code
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.username == key))
            asset_id = db.scalar(select(Asset.id).order_by(Asset.id).limit(1))
        login = client.post("/login", json={"username": key, "password": password})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        response = client.post("/simulations", headers=headers, json={
            "asset_id": asset_id, "initial_investment": "1000.00",
            "purchase_date": "2023-01-02", "valuation_date": "2024-01-02",
        })
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
        await_status(response.json()["id"], "completed")
        assert client.get(f"/simulations/{response.json()['id']}", headers=headers).json()["status"] == "completed"
        print("PASS: authenticated API -> pending -> Celery -> completed ($1200 fictional value)")

    def create(**fields):
        with SessionLocal() as db:
            row = Simulation(user_id=user_id, asset_id=asset_id, initial_investment=Decimal("1000"),
                             purchase_date=date(2023, 1, 2), valuation_date=date(2024, 1, 2), **fields)
            db.add(row)
            db.commit()
            return row.id

    pending_id = create()
    original_publish = process_simulation_task.apply_async
    def unavailable(**kwargs):
        raise OperationalError("integration: broker unavailable")
    process_simulation_task.apply_async = unavailable
    try:
        with SessionLocal() as db:
            dispatch_simulations(db, pending_id)
    finally:
        process_simulation_task.apply_async = original_publish
    with SessionLocal() as db:
        row = db.get(Simulation, pending_id)
        assert row.dispatch_attempts == 1 and row.status == "pending"
        row.next_dispatch_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    await_status(pending_id, "completed")
    print("PASS: simulated publication outage -> automatic recovery scanner -> real Celery completion")

    expired_id = create(status="running", processing_token="crashed-worker", processing_attempts=1,
                        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    await_status(expired_id, "completed")
    print("PASS: abandoned running lease -> automatic recovery -> completed")

    exhausted_id = create(dispatch_attempts=12)
    await_status(exhausted_id, "failed")
    print("PASS: exhausted dispatch budget -> automatic terminal failure")

    queue = "verify-" + uuid4().hex
    failure_worker = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "larp_finance.celery_app:celery_app", "worker",
         "--concurrency=1", "--loglevel=ERROR", "--without-gossip", "--without-mingle", "--without-heartbeat",
         "-Q", queue, "-n", queue + "@%h"],
        env={**os.environ, "LARP_SIMULATION_MODE": "unsupported"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    failed_id = create(next_dispatch_at=datetime.now(timezone.utc) + timedelta(hours=1))
    process_simulation_task.apply_async(args=[failed_id], queue=queue, retry=False)
    await_status(failed_id, "failed")
    print("PASS: real Celery provider configuration failure -> failed, claim cleared")
finally:
    if failure_worker is not None:
        failure_worker.terminate()
        try:
            failure_worker.wait(timeout=15)
        except subprocess.TimeoutExpired:
            failure_worker.kill()
            failure_worker.wait(timeout=5)
    if user_id is not None:
        with SessionLocal() as db:
            db.execute(delete(Simulation).where(Simulation.user_id == user_id))
            db.execute(delete(Portfolio).where(Portfolio.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
        print("Removed integration-only user, portfolio and simulations")
