import hashlib
import json
from datetime import datetime, timezone
from time import monotonic, sleep

from larp_finance.services.historical_errors import TemporaryHistoricalPriceError


CACHE_TTL = 21600
RESERVE_CREDIT = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
if tonumber(redis.call('GET', KEYS[2]) or '0') >= 800 then return -1 end
redis.call('SET', KEYS[1], '1', 'EX', 8)
redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], 172800)
return 1
"""


class HistoricalPriceCache:
    def __init__(self, redis, api_key):
        self.redis = redis
        self.account = hashlib.sha256(api_key.encode()).hexdigest()

    def key(self, symbol, asset_type, start, end):
        identity = f"v1:splits:USD:{self.account}:{asset_type}:{symbol}:{start}:{end}"
        return "history:" + hashlib.sha256(identity.encode()).hexdigest()

    def get(self, key):
        raw = self.redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            self.redis.delete(key)
            return None

    def put(self, key, values):
        self.redis.set(key, json.dumps(values), ex=CACHE_TTL)

    def reserve_credit(self):
        gap = f"history:quota:{self.account}:gap"
        deadline = monotonic() + 10
        while True:
            today = datetime.now(timezone.utc).date()
            result = self.redis.eval(RESERVE_CREDIT, 2, gap,
                                     f"history:quota:{self.account}:{today}")
            if result == 1:
                return
            if result == -1:
                raise TemporaryHistoricalPriceError("Historical data daily quota reached", retry_after=86400)
            delay = max(1, self.redis.ttl(gap))
            if delay > 8 or monotonic() + delay > deadline:
                raise TemporaryHistoricalPriceError("Historical data request rate limited", retry_after=delay)
            sleep(delay)

    def cooldown(self, seconds):
        key = f"history:quota:{self.account}:gap"
        self.redis.eval("""
if redis.call('TTL', KEYS[1]) < tonumber(ARGV[1]) then
    redis.call('SET', KEYS[1], '1', 'EX', ARGV[1])
end
""", 1, key, max(60, min(seconds, 86400)))

    def lock(self, key):
        return self.redis.lock(key + ":lock", timeout=90, blocking_timeout=0)
