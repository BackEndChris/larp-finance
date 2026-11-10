"""Docker verification: mocked provider HTTP, real API/Redis/PostgreSQL/Celery."""
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import delete, select

from larp_finance import tasks
from larp_finance.database import SessionLocal
from larp_finance.main import app
from larp_finance.models import Asset, Portfolio, Simulation, User
from larp_finance.services.historical_cache import HistoricalPriceCache

key = "RealVerify" + uuid4().hex[:12]
queue = key.lower()
api_key = "verification-only-" + key
account = hashlib.sha256(api_key.encode()).hexdigest()
redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
cache_keys = queue + ":cache-keys"
request_counter = queue + ":requests"
user_id = None
worker = None
original_publish = tasks.process_simulation_task.apply_async
original_mode = os.environ.get("LARP_SIMULATION_MODE")

bootstrap = '''
import os
import httpx
from redis import Redis
from larp_finance import tasks
from larp_finance.celery_app import celery_app
from larp_finance.services.historical_cache import HistoricalPriceCache
from larp_finance.services.twelve_data import TwelveDataHistoricalPriceProvider

redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
class VerificationCache(HistoricalPriceCache):
    def key(self, *args):
        key = super().key(*args)
        redis.sadd(os.environ["VERIFY_CACHE_KEYS"], key)
        return key

def respond(request):
    symbol = request.url.params["symbol"]
    count = redis.incr(os.environ["VERIFY_COUNTER"] + ":" + symbol)
    if symbol == "SOL/USD":
        return httpx.Response(401)
    if symbol == "ETH/USD" and count == 1:
        return httpx.Response(503)
    meta = dict(symbol=symbol, interval="1day")
    if "/" in symbol:
        meta.update(currency_quote="US Dollar", exchange_timezone="UTC")
    else:
        assert request.url.params["adjust"] == "splits"
        meta.update(currency="USD", exchange_timezone="America/New_York")
    return httpx.Response(200, json=dict(status="ok", meta=meta, values=[
        dict(datetime="2020-08-28", close="124.8075"),
        dict(datetime="2020-08-31", close="129.04"),
    ]))

tasks.TwelveDataHistoricalPriceProvider = lambda: TwelveDataHistoricalPriceProvider(
    os.environ["TWELVE_DATA_API_KEY"],
    cache=VerificationCache(redis, os.environ["TWELVE_DATA_API_KEY"]),
    transport=httpx.MockTransport(respond),
)
celery_app.worker_main(["worker", "--concurrency=1", "--loglevel=ERROR", "--without-gossip",
                        "--without-mingle", "--without-heartbeat", "-Q", os.environ["VERIFY_QUEUE"],
                        "-n", os.environ["VERIFY_QUEUE"] + "@%h"])
'''


def await_status(simulation_id, status):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            row = db.get(Simulation, simulation_id)
            if row.status == status:
                return
        time.sleep(0.1)
    raise AssertionError(f"Expected {status} for integration simulation")


try:
    worker = subprocess.Popen([sys.executable, "-c", bootstrap], env={**os.environ,
        "TWELVE_DATA_API_KEY": api_key, "VERIFY_QUEUE": queue,
        "VERIFY_CACHE_KEYS": cache_keys, "VERIFY_COUNTER": request_counter},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.environ["LARP_SIMULATION_MODE"] = "real"
    tasks.process_simulation_task.apply_async = lambda **kwargs: original_publish(queue=queue, **kwargs)
    with TestClient(app) as client:
        password = uuid4().hex + "Aa1!"
        response = client.post("/register", json=dict(username=key, email=key + "@example.com", password=password))
        assert response.status_code == 201
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.username == key))
            assets = dict(db.execute(select(Asset.symbol, Asset.id)).all())
        token = client.post("/login", json=dict(username=key, password=password)).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        def create(symbol):
            response = client.post("/simulations", headers=headers, json=dict(
                asset_id=assets[symbol], initial_investment="1000.00",
                purchase_date="2020-08-28", valuation_date="2020-08-31"))
            assert response.status_code == 201
            assert response.json()["data_source"] == "twelve_data"
            return response.json()["id"]
        for _ in range(2):
            simulation_id = create("AAPL")
            await_status(simulation_id, "completed")
            result = client.get(f"/simulations/{simulation_id}", headers=headers).json()
            assert result["final_value"] == "1033.91"
            assert result["actual_purchase_date"] == "2020-08-28"
            assert result["actual_valuation_date"] == "2020-08-31"
        assert redis.get(request_counter + ":AAPL") == "1"
        print("PASS: real-mode API -> Celery -> split-adjusted result; second job uses shared Redis cache", flush=True)
        simulation_id = create("ETH")
        await_status(simulation_id, "pending")
        # Wait until the first claim has actually failed rather than observing initial pending.
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            with SessionLocal() as db:
                row = db.get(Simulation, simulation_id)
                if row.retry_not_before is not None:
                    assert row.processing_attempts == 1
                    assert row.processing_token is None
                    row.retry_not_before = datetime.now(timezone.utc) - timedelta(seconds=1)
                    row.next_dispatch_at = datetime.now(timezone.utc) + timedelta(hours=1)
                    db.commit()
                    break
            time.sleep(0.1)
        else:
            raise AssertionError("Transient provider failure did not schedule a retry")
        original_publish(args=[simulation_id], queue=queue, retry=False)
        await_status(simulation_id, "completed")
        print("PASS: real Celery transient provider error -> durable delayed retry -> completion", flush=True)
        simulation_id = create("SOL")
        await_status(simulation_id, "failed")
        assert redis.get(request_counter + ":SOL/USD") == "1"
        print("PASS: permanent provider authentication failure stops after one attempt", flush=True)
finally:
    tasks.process_simulation_task.apply_async = original_publish
    if original_mode is None:
        os.environ.pop("LARP_SIMULATION_MODE", None)
    else:
        os.environ["LARP_SIMULATION_MODE"] = original_mode
    if worker is not None:
        worker.terminate()
        try:
            worker.wait(timeout=15)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=5)
    if user_id is not None:
        with SessionLocal() as db:
            db.execute(delete(Simulation).where(Simulation.user_id == user_id))
            db.execute(delete(Portfolio).where(Portfolio.user_id == user_id))
            db.execute(delete(User).where(User.id == user_id))
            db.commit()
    for cache_key in redis.smembers(cache_keys):
        redis.delete(cache_key, cache_key + ":lock")
    for quota_key in redis.scan_iter(match="history:quota:" + account + ":*"):
        redis.delete(quota_key)
    for counter in redis.scan_iter(match=request_counter + "*"):
        redis.delete(counter)
    redis.delete(cache_keys)
    print("Removed verification-only database records and Redis keys", flush=True)
