# Architecture and operations

All commands in this document run from the repository root. Start with the
[README](../README.md) for configuration, Docker startup and the API walkthrough.

## Code map

| Component | Responsibility |
| --- | --- |
| `src/larp_finance/main.py` | FastAPI application, API metadata and router registration |
| `routers/` | JSON contracts, authentication dependencies, HTTP errors and ownership filters |
| `schemas.py` | Pydantic request/response validation; decimal money/quantity values |
| `models.py`, `database.py` | SQLAlchemy mappings and request-scoped sessions |
| `alembic/versions/` | Ordered PostgreSQL schema migrations; no runtime create_all |
| `security.py`, `auth.py` | Argon2 hashing, HS256 access tokens and current-user lookup |
| `services/trading.py`, `market_data.py` | Atomic virtual trades and cached Alpha Vantage quotes |
| `services/simulation_engine.py` | Pure Decimal buy-and-hold calculation |
| `services/simulation_service.py`, `price_selection.py` | Provider-independent orchestration and date selection |
| `services/historical_prices.py` | Structural provider Protocol returning date-to-Decimal closes |
| `services/twelve_data.py`, `historical_cache.py` | Real history normalization, Redis cache/quotas |
| `services/simulation_processing.py` | Claims, leases, ownership checks and result persistence |
| `services/simulation_dispatch.py`, `simulation_recovery.py` | Durable dispatch and bounded abandoned-job recovery |
| `celery_app.py`, `tasks.py` | Redis-backed Celery configuration and worker-owned sessions |
| `Tests/`, `scripts/` | Isolated pytest cases and explicit Docker integration checks |

## Authentication, ownership and trading

Registration atomically inserts the user and a portfolio containing $10,000 in
fictional cash. Passwords are stored as Argon2 hashes. Access tokens require sub
and exp claims, use HS256 and expire after 30 minutes; authentication also checks
that the subject still identifies an existing user. JWT_SECRET_KEY has no runtime
fallback and cannot be blank. There is no refresh/revocation or login rate limit.

Portfolio and trade queries derive ownership from the authenticated user.
Simulation lookups filter both simulation ID and user ID, returning 404 for a
missing or unowned row. Asset listings/quotes are public. Generic addition-task
results are authenticated but not owner-scoped; they expose task state/result by
UUID and are a retained Celery demonstration. This limitation should be addressed
in the comprehensive audit before treating that endpoint as a general task API.
Simulation results are accessed through their own owner-filtered database route,
not the generic Celery result route.

A trade retrieves its quote before taking the portfolio FOR UPDATE lock. A single
transaction adjusts cash, holding quantity/average cost and inserts the trade.
Competing operations on a portfolio serialize on that lock; tests exercise real
PostgreSQL sessions to prevent overspending/overselling. Read transactions can
exist during quote retrieval, but the portfolio write lock is not held then.

Idempotency keys are required HTTP headers, limited to 64 characters and unique
within a portfolio. Existing matching trades return without another mutation;
a different asset, quantity or direction with the same key yields 409. The key is
checked again after locking to handle concurrent requests. Quantities/prices use
Decimal/Numeric; trade totals round half up to cents and trades must be at least
$1. Oversized values and cash/holding conflicts are rejected. Failed commits roll
back; request sessions close on exit.

Spot quotes are Alpha Vantage GLOBAL_QUOTE (stocks) or CURRENCY_EXCHANGE_RATE
(crypto), cached for one hour within each API process. Multiple API processes do
not share this cache. Trades require USD, finite positive prices and usable quote
timestamps: stock age at most five UTC calendar days, crypto age at most two hours
and at most five minutes into the future. Naive crypto timestamps are interpreted
as UTC. Provider errors/malformed prices yield safe 503 responses. Historical
mode does not alter this path or give trades demo quotes. Keep provider keys out
of logs; Alpha Vantage's existing API authentication uses a query parameter.

## Asynchronous simulation lifecycle

Compose starts a database initializer, API, Linux prefork worker and independent
recovery process. The initializer migrates and seeds after PostgreSQL is healthy.
The API/worker/scanner wait for successful initialization; the worker also waits
for Redis. The API can accept a committed simulation during broker downtime.
The root endpoint only returns a welcome message, not dependency health.

The committed simulation row doubles as its durable dispatch record. Creation
commits before best-effort task publication and returns a pending response. The
publication transaction locks the row; concurrent scanners use SKIP LOCKED.
A crash or lost publish acknowledgement may duplicate messages. There is no
claim of exactly-once message delivery: database ownership checks protect results.

Each processing task opens/closes its own SQLAlchemy session. It claims a pending
row or expired running lease with FOR UPDATE, generates a UUID token, increments
processing_attempts, assigns a ten-minute lease and commits. Only plain inputs
cross into the historical calculation; no transaction or row lock remains open
during that calculation. Before either success or failure writes, the worker
locks/reloads the row and checks running status, matching token and an unexpired
lease against PostgreSQL clock_timestamp(). A stale/expired worker discards its
result even if no replacement has finished. Terminal writes clear token/lease.
Completed and failed rows cannot be claimed again.

A dedicated `python -m larp_finance.simulation_recovery` process scans every
15 seconds, up to 50 rows per scan. Pending rows due for publication and abandoned
running rows (expired/missing lease) are eligible. Republishing uses delays of
60, 120, 180, 240 then 300 seconds. There are at most 12 publication attempts and
three processing claims per simulation. Exhausted work becomes failed; restoring
Redis does not automatically reopen terminal failures. Keep the scanner running.

Celery discovers `larp_finance.tasks`, including add_numbers and
process_simulation_task. Worker prefetch is one; simulation tasks acknowledge late,
ignore Celery results and use 480-second soft/540-second hard time limits below
the 600-second lease. Worker-loss rejection is disabled to avoid immediate endless
redelivery; lease recovery handles abandoned work. Linux prefork is required for
hard limits; native Windows solo is insufficient. Redis broker connection/socket
timeouts are three seconds, publication retry is disabled in the dispatcher.

SQLAlchemy errors roll back and escape without being converted into permanent
calculation failures; the scanner recovers uncertain claims/commits. Permanent
calculation/provider errors fail immediately. Transient historical errors set a
pending state, next_dispatch_at and retry_not_before while clearing ownership.
That separate retry gate prevents duplicate messages from skipping the delay.
Retries share the same claim/publication budgets and do not use Celery autoretry.
GET /simulations/{id} is the source of status, results and safe error messages.

Operational commands:

```powershell
docker compose --env-file .env.docker logs --tail 50 api worker recovery
docker compose --env-file .env.docker exec -T api alembic current
docker compose --env-file .env.docker exec -T api alembic check
```

Changing a database password in an env file does not update an existing PostgreSQL
volume. API signing-key changes invalidate previously issued tokens. Recreate
services after environment changes. A fresh `up --build -d` runs initialization;
seed inserts are idempotent. Do not erase volumes as a routine troubleshooting step.

## Historical data policy

The following provider and financial policies apply to real historical mode.
Demo mode is explicitly fictional and does not model trading calendars. Provider
comparison facts were checked on 2026-11-10; account limits/terms may change.

### Provider selection

Research checked 2026-11-10 using provider documentation. Twelve Data is selected
for both asset types, avoiding another account, adapter and market-price basis.
Existing Alpha Vantage spot quotes are unchanged.

| Option | Daily history, coverage and adjustments | Cost/access and decision |
| --- | --- | --- |
| Twelve Data | Stock and crypto daily OHLC; explicit `adjust=splits`; instrument-dependent depth. Map AAPL/MSFT/NVDA/TSLA to NASDAQ and BTC/ETH/SOL to USD pairs. | Basic lists 8 credits/minute and 800/day; time_series costs one credit/symbol/request. API key required. Selected for development; individual symbol entitlements/history must be verified with your account. |
| Alpha Vantage | Raw stock daily prices, premium daily adjusted data with splits/dividends, and cryptocurrency daily data. Advertises 25+ years for equities. | Standard free quota is 25 requests/day. Existing quote key does not imply access to the premium adjusted endpoint. Rejected to avoid depending on a paid stock-adjustment endpoint. |
| CoinGecko | Crypto coverage but no equities. Historical chart endpoints offer daily data, with the Demo plan limited to the past year. | Separate key/account and a stock adapter still required. Rejected for the limited free historical window and extra integration. |
| Coinbase Exchange | Public exchange-specific BTC/USD, ETH/USD and SOL/USD candles, subject to listing history; not a consolidated crypto close. No stocks. Candles can be incomplete and requests cap at 300 points. | Public candle requests need no trading credentials, but require pagination and a separate stock provider. Rejected as unnecessary complexity for this commit. Public API access does not itself grant redistribution rights. |

Sources:
- [Twelve Data time series](https://twelvedata.com/docs/market-data/time-series)
- [Twelve Data pricing](https://twelvedata.com/pricing)
- [Twelve Data cryptocurrency coverage](https://twelvedata.com/cryptocurrency)
- [Twelve Data adjustment policy](https://support.twelvedata.com/en/articles/5179064-are-the-prices-adjusted)
- [Alpha Vantage endpoints](https://www.alphavantage.co/documentation/)
- [Alpha Vantage free quota](https://www.alphavantage.co/support/)
- [CoinGecko historical limits](https://www.coingecko.com/learn/coingecko-api-troubleshooting-guide-and-solutions)
- [Coinbase candle endpoint](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)

### Configuration and provenance

Set `LARP_SIMULATION_MODE=demo` or `real` for the API. Real mode requires
`TWELVE_DATA_API_KEY` in the worker environment. Use `.env` for local operation or
`.env.docker` for Compose; do not commit either. Restart/recreate services after
configuration changes. No paid account is purchased or enabled by this code.
Redis (`REDIS_URL`) is required for real-mode cache/quota coordination. Compose
already supplies Redis and database URLs and defaults the API/worker mode to demo.

    uv sync --locked
    uv run alembic upgrade head
    docker compose --env-file .env.docker up --build -d

A new simulation stores `data_source=demo` or `twelve_data` at creation, before
publication. The worker uses this saved source, not a later environment default.
Switching back to demo does not turn pending real jobs into fictional results;
keep the key configured until those jobs finish. There is no fallback to demo.
A worker may therefore process both previously queued sources. Missing mode
configuration prevents new API simulation creation; missing keys fail real jobs
with a safe configuration message. Unknown assets/sources fail explicitly.

Migration `e23b0011abcd` follows `d22a0010abcd` and adds `data_source`,
`actual_purchase_date`, `actual_valuation_date`, and `retry_not_before`. Existing
Commit 22 rows are labeled demo. Existing completed rows retain null actual dates
because the historical selected dates were not stored; they are not invented.
These three public metadata fields are added to simulation responses.

### Price and date policy

Stocks request NASDAQ daily closes with `adjust=splits`, excluding dividend
adjustments. The calculation is a split-adjusted price return, excluding cash
dividends, reinvestment, fees and taxes. Quantity is in the provider's adjusted
share units, not necessarily the number of shares held on the purchase date.
Splits after either requested date may rescale both prices and quantity; the
investment return remains consistent when both prices share the same basis.
This is not total-return performance. Crypto requests unadjusted USD daily closes
from Twelve Data's feed, not execution prices on a specified exchange.

Every provider range uses one response, so both ends share one adjustment
snapshot. Requests are capped at 4999 inclusive calendar days (~13.7 years),
including the calculation service's seven-day padding at each end. Longer ranges
fail explicitly rather than risking the endpoint's 5000-point truncation or mixing
cached split bases across pages. This is a per-simulation span limit, not a promise
that history exists for every asset/date. Pre-listing and unavailable data fail.

Stock dates use America/New_York and crypto dates use UTC. The entire current
market-local calendar date is excluded, even after its normal closing time. This
conservative policy avoids unfinished/late daily bars without a full exchange
calendar. Valuation today can therefore use an earlier completed close.

Purchases select the first available close on or after the requested date;
valuations select the last available close on or before it. Maximum gaps are seven
calendar days for stocks and one for crypto. Weekends/holidays are handled by
available observations; gaps beyond these limits fail. Selected purchase dates
cannot exceed selected valuation dates. The API preserves requested dates and
separately returns actual selected dates. No price is interpolated or fabricated.

Closes are parsed directly as Decimal (including numeric JSON tokens). Malformed
rows, duplicate dates, wrong symbol/currency/timezone, non-finite/non-positive
prices, and prices outside the database's supported scale/range are rejected.
Only seeded assets are supported in this adapter. Price columns retain their
existing eight-decimal database precision; provider precision is used for the
calculation before storage rounding. Historical corrections and feed differences
remain possible; this is a portfolio simulation, not an execution/backtesting feed.

### Cache, quota and failure behavior

The existing spot cache is process-local and cannot coordinate Celery workers.
Historical data therefore uses Redis instead: exact asset/range/account/version
keys, validated string prices and a six-hour TTL. Entire ranges are cached
atomically; old and newly adjusted subranges are not combined. Keys include a
hash of the API key, never the key itself. A 90-second distributed fetch lock
limits duplicate requests; cache hits do not consume a credit. Invalid cached data
is discarded. Redis failure delays the job rather than bypassing quota controls.

An atomic Redis script spaces requests at least eight seconds apart across
workers and limits this adapter to 800 reservations per UTC day/account. It waits
at most ten seconds for a local credit, then schedules a retry. Other applications
using the same key are not counted here; provider limits remain authoritative.
Redis data loss also resets local accounting. HTTP 429 responses establish a
shared cooldown (numeric Retry-After, otherwise 300 seconds). Daily local quota
exhaustion waits 24 hours. Cache expiration allows provider corrections to appear;
completed simulations remain stored snapshots rather than being recalculated.

HTTP connect/write/pool timeouts are five seconds; read timeout is twenty seconds.
Authentication uses the Authorization header, not URL query strings. Redirects
are rejected. Raw provider messages, HTTP exception text and credentials are not
stored in simulation errors or rethrown to Celery logs.

Network errors, HTTP 408/429/5xx, matching provider JSON errors, and Redis failures
schedule durable delayed retries with token/lease checks. Auth/entitlement errors,
unsupported symbols, missing history and invalid responses fail immediately.
Three processing claims and twelve publication attempts remain the total budgets.
`retry_not_before` prevents duplicate messages bypassing the provider delay.
The scanner publishes due retries without Celery automatic retry loops.

### Integration checks

Automated pytest cases mock external HTTP and do not require live API keys or
consume provider quota. They retain PostgreSQL concurrency coverage. Run:

    uv run pytest -q
    docker compose --env-file .env.docker exec -T api alembic check
    Get-Content scripts/verify_async_integration.py | docker compose --env-file .env.docker exec -T worker python -u -
    Get-Content scripts/verify_real_history_integration.py | docker compose --env-file .env.docker exec -T worker python -u -

The first script exercises demo/recovery through the running API. The second
uses an in-process authenticated API with the actual Docker database/broker and
an isolated real Celery worker. Only that worker's external HTTP is mocked; it
checks real-mode source/date persistence, shared Redis caching, delayed retries
and permanent errors. Both scripts remove their own temporary records/keys.
They do not certify live provider availability, symbol entitlement or licensing.

Live checks require a configured Twelve Data key. Add your own
key and select real mode, then perform a small authenticated stock and crypto
check before relying on live behavior. SOL/USD and historical depth depend on
current provider coverage and your account; unsupported requests fail visibly.
No live genuine-price verification is claimed by the deterministic scripts.

### Licensing

Twelve Data's terms limit free/individual use and separately control external
display, redistribution, derived data, attribution and retention. Non-production
development/educational use does not automatically authorize a public portfolio
website or commercial use. This API exposes underlying prices, so do not assume
its results qualify as irreversible derived data. Keep public demonstrations in
demo mode unless your account/data agreements permit the intended display.
Confirm retention rights for both the six-hour cache and stored simulation prices;
purge provider data as required when an agreement ends. No public/commercial
license, entitlement or availability guarantee is supplied by this integration.

- [Terms and retention restrictions](https://twelvedata.com/terms)
- [Personal, commercial, derived-data and attribution guidance](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage)


## Testing and review boundaries

Tests verify the actual database name before migrating, then use an outer
transaction with join_transaction_mode=create_savepoint for most cases.
Concurrency/integration tests deliberately commit through independent sessions
and clean up their own records. The name check is a guard, not permission to use
an important database named larp_finance_test. Isolate the test instance.

Ordinary pytest uses mocked upstream HTTP and broker publication; it needs no
market-data credentials or Redis. Docker scripts additionally exercise Redis,
Celery and the recovery loop. The real-history script mocks provider HTTP and
cannot establish live entitlement, price accuracy or licensing. CI uses a public
job-local test JWT key and PostgreSQL 18 so fork PRs do not depend on repository
secrets. Docker uses PostgreSQL 17. Windows is supported through Compose/WSL.

This is a development setup: the worker runs as container root, startup is not a
production deployment policy, and no SLA, rate-limited authentication, generic
task ownership, full exchange calendar or holdings-list API is promised. The next
phase is a comprehensive audit; presentation polish does not replace that review.
