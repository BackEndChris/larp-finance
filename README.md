# LARP Finance

A Python backend for virtual USD investing and historical buy-and-hold simulations.
Built as a portfolio project to demonstrate API design, relational transactions,
background processing, and testing. It never moves real money or executes real trades.

## What it does

- Register users, hash passwords with Argon2, and authenticate with expiring JWTs.
- Give each user a portfolio with **$10,000 fictional cash**.
- Buy and sell seeded stocks/crypto using Alpha Vantage quotes, with cash/holding
  checks, PostgreSQL row locks, and idempotent trade requests.
- Retrieve the current user's cash balance and paginated trade history.
- Calculate historical buy-and-hold results asynchronously through Celery.
- Recover missed publications and abandoned simulations with PostgreSQL-backed
  dispatch state, ownership tokens, leases, and bounded retries.
- Keep explicitly fictional demo simulations separate from Twelve Data results.

Seeded assets: **AAPL, MSFT, NVDA, TSLA, BTC, ETH, SOL**.

The stack is Python 3.13, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis,
Celery, Docker Compose, pytest, GitHub Actions, and uv.

## Architecture at a glance

```mermaid
flowchart LR
    Client[API client / Swagger UI] --> API[FastAPI]
    API --> DB[(PostgreSQL)]
    API --> Quotes[Alpha Vantage spot quotes]
    API --> Redis[(Redis broker/cache)]
    Recovery[Recovery scanner] --> DB
    Recovery --> Redis
    Redis --> Worker[Celery worker]
    Worker --> DB
    Worker --> History[Demo prices or Twelve Data]
```

PostgreSQL is the source of truth for users, portfolios, trades and simulations.
Trade mutations commit atomically. Simulations commit before task publication;
workers calculate outside the claim transaction and check ownership before saving.
Redis carries messages and coordinates historical caching/quotas. The scanner
recovers work even if the original publish failed.

See [architecture and operations](docs/architecture.md) for transactions, recovery,
price policies, provider selection/licensing, and technical limitations.
[Development.md](Development.md) is the author's chronological development diary.

## Run with Docker Compose

### Prerequisites

- Git and Docker Desktop running with Linux containers (WSL2 on Windows).
- Docker Compose (`docker compose version`).
- PowerShell; the commands below work from the repository root on Windows.
- Python 3.13 and uv are needed for local development/tests, not the Docker startup.

### Configure the environment

For a fresh checkout, copy the template without replacing an existing file:

```powershell
if (-not (Test-Path .env.docker)) { Copy-Item .env.example .env.docker }
```

Edit `.env.docker`. Set **POSTGRES_PASSWORD** and **JWT_SECRET_KEY** to different,
random values. This PowerShell snippet prints a random hex value; run it twice:

```powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 32
$rng.GetBytes($bytes)
[BitConverter]::ToString($bytes).Replace('-', '')
$rng.Dispose()
```

Use the generated hex password directly; other passwords containing URL-special
characters require URL encoding when inserted into a database URL. Keep both
`.env` and `.env.docker` private; they are Git-ignored and excluded from builds.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Password used to initialize the Compose PostgreSQL user. Required by Compose. |
| `JWT_SECRET_KEY` | Required JWT signing secret. Blank values fail startup. Tokens expire after 30 minutes. |
| `DATABASE_URL` | SQLAlchemy `postgresql+psycopg://...` URL. Compose sets the correct `db:5432` URL for every application service. |
| `REDIS_URL` | Broker/result/cache URL. Compose sets `redis://redis:6379/0`. |
| `LARP_SIMULATION_MODE` | `demo` (Compose default) or `real`, applied to newly created simulations. |
| `ALPHA_VANTAGE_API_KEY` | Required for spot quotes **and virtual trades**, including when historical mode is `demo`. |
| `TWELVE_DATA_API_KEY` | Required in the worker for real historical simulations. Not needed for demo history. |
| `TEST_DATABASE_URL` | Separate database named exactly `larp_finance_test`; used only by pytest. See below. |

**Key-free evaluation:** leave provider keys blank and use historical demo mode.
Registration, login, portfolio retrieval, asset listing and demo simulations work;
spot quotes/trades return 503 without a working Alpha Vantage key. Demo history
uses fictional $100 purchase and $120 valuation prices; it does not change trading quotes.

### Start and inspect

```powershell
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 30 init worker recovery
Invoke-RestMethod http://127.0.0.1:8000/
```

Expected root response: `{"message":"Welcome to Larp Finance!"}`.

- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- OpenAPI schema: [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

The `db` and `redis` services have health checks. `init` applies all Alembic
migrations and seeds assets idempotently, then exits successfully. API, worker and
recovery wait for initialization; the worker also waits for Redis. An exited
`init` container with exit code 0 is expected. No manual migration or seeding step
is needed for normal Compose startup. The API binds only to localhost; PostgreSQL
and Redis are not published to host ports.

Check migration consistency or stop without deleting data:

```powershell
docker compose --env-file .env.docker exec -T api alembic current
docker compose --env-file .env.docker exec -T api alembic check
docker compose --env-file .env.docker down
```

PostgreSQL data persists in the named volume. Changing `POSTGRES_PASSWORD` later
does not change the password inside an existing volume; update the database role
and configuration together. Avoid `down --volumes` unless you intend to erase data.

## Demonstration workflow (PowerShell)

Run sections in order against the started application. IDs and current prices
are discovered dynamically. Use a new username/email each time. Money is sent as
JSON strings and returned as decimal strings.

### 1. Register, log in, and inspect your portfolio

```powershell
$base = 'http://127.0.0.1:8000'
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 10)
$username = "Reviewer$suffix"
$password = [guid]::NewGuid().ToString('N') + 'Aa1!'
$registration = @{ username = $username; email = "$username@example.com"; password = $password } | ConvertTo-Json
$user = Invoke-RestMethod -Method Post -Uri "$base/register" -ContentType 'application/json' -Body $registration
$loginBody = @{ username = $username; password = $password } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$base/login" -ContentType 'application/json' -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "$base/users/me" -Headers $headers
Invoke-RestMethod "$base/portfolio/me" -Headers $headers
$assets = Invoke-RestMethod "$base/assets"
$asset = $assets | Where-Object symbol -EQ 'AAPL'
```

Example portfolio response (IDs/timestamps vary):

```json
{"id":1,"user_id":1,"cash_balance":"10000.00","created_at":"2026-11-11T10:00:00Z"}
```

A portfolio is created during registration; there is no deposit/reset endpoint.
The portfolio endpoint currently returns cash, not a holdings/valuation dashboard.

### 2. Buy, replay safely, and sell a virtual asset

This section requires a working Alpha Vantage key. Skip to simulations for a
key-free demo. Provider quotas, entitlements, outdated quotes or outages can return
503; the API does not substitute invented trading prices.

```powershell
Invoke-RestMethod "$base/assets/AAPL/quote"
$tradeHeaders = @{ Authorization = $headers.Authorization; 'Idempotency-Key' = [guid]::NewGuid().ToString('N') }
$tradeBody = @{ asset_id = $asset.id; quantity = '1' } | ConvertTo-Json
$buy = Invoke-RestMethod -Method Post -Uri "$base/trades/buy" -Headers $tradeHeaders -ContentType 'application/json' -Body $tradeBody
# Same key and body return the existing trade, without another debit.
$replay = Invoke-RestMethod -Method Post -Uri "$base/trades/buy" -Headers $tradeHeaders -ContentType 'application/json' -Body $tradeBody
$buy.id -eq $replay.id
$tradeHeaders['Idempotency-Key'] = [guid]::NewGuid().ToString('N')
$sell = Invoke-RestMethod -Method Post -Uri "$base/trades/sell" -Headers $tradeHeaders -ContentType 'application/json' -Body $tradeBody
Invoke-RestMethod "$base/portfolio/me" -Headers $headers
Invoke-RestMethod "$base/trades?limit=10&offset=0" -Headers $headers
```

Trades must be at least $1 and fit available cash/holdings. Example trade response
at an **illustrative** $200 quote (not a promised live price):

```json
{"id":1,"portfolio_id":1,"asset_id":1,"trade_type":"buy","quantity":"1.000000000000","unit_price":"200.00000000","total_amount":"200.00000000","created_at":"2026-11-11T10:00:01Z"}
```

Reusing a key for a different asset, quantity or direction returns 409. Use a new
key for a new intended trade. Users can only access their own portfolio/trades.

### 3. Create a simulation and retrieve its result

Keep `LARP_SIMULATION_MODE=demo` for this deterministic example. Historical
simulations are independent of portfolio cash/holdings and do not place trades.

```powershell
$simulationBody = @{ asset_id = $asset.id; initial_investment = '1000.00'; purchase_date = '2023-01-02'; valuation_date = '2024-01-02' } | ConvertTo-Json
$simulation = Invoke-RestMethod -Method Post -Uri "$base/simulations" -Headers $headers -ContentType 'application/json' -Body $simulationBody
$simulation | Select-Object id, status, data_source
$deadline = (Get-Date).AddSeconds(60)
do {
    $result = Invoke-RestMethod "$base/simulations/$($simulation.id)" -Headers $headers
    if ($result.status -in @('completed', 'failed')) { break }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
$result
```

Creation returns HTTP 201 with `status=pending`. In demo mode a successful result
contains the following fields; the actual response also includes IDs, requested
inputs and timestamps:

```json
{
  "status":"completed",
  "data_source":"demo",
  "actual_purchase_date":"2023-01-02",
  "actual_valuation_date":"2024-01-02",
  "purchase_price":"100.00000000",
  "final_price":"120.00000000",
  "final_value":"1200.00",
  "profit_loss":"200.00",
  "error_message":null
}
```

Demo dates/prices are fictional and do not model trading calendars. With real
mode, actual trading dates can differ from requested dates. Pending/running jobs
may outlast this polling window during retries; inspect worker/recovery logs and
poll again. Another user's simulation ID returns 404.

To enable genuine history, set `LARP_SIMULATION_MODE=real` and supply a
`TWELVE_DATA_API_KEY` in `.env.docker`, then rerun `up --build -d`. Newly created
jobs record `data_source=twelve_data`. Existing jobs retain their original source.
Real history has no fictional fallback. Read the [price and licensing policies](docs/architecture.md#historical-data-policy)
before interpreting results or displaying provider data publicly.

## API overview

All request bodies are JSON. Protected endpoints use `Authorization: Bearer <token>`;
Swagger's **Authorize** dialog accepts the token from `/login`. Login uses JSON,
not an OAuth form. Full schemas and validation details are available in `/docs`.

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| GET | `/` | Public | Welcome response; not a dependency health probe |
| POST | `/register` | Public | Create user and $10,000 portfolio (201) |
| POST | `/login` | Public | Obtain a 30-minute bearer token |
| GET | `/users/me` | Bearer | Current user |
| GET | `/portfolio/me` | Bearer | Own cash balance |
| GET | `/assets` | Public | Seeded asset IDs/symbols |
| GET | `/assets/{symbol}/quote` | Public | Alpha Vantage spot quote |
| POST | `/trades/buy` | Bearer + `Idempotency-Key` | Virtual purchase (201, including replay) |
| POST | `/trades/sell` | Bearer + `Idempotency-Key` | Virtual sale (201, including replay) |
| GET | `/trades?limit=50&offset=0` | Bearer | Own trade history; limit 1–100 |
| POST | `/simulations` | Bearer | Persist and queue simulation (201) |
| GET | `/simulations/{id}` | Bearer | Own simulation status/result |
| POST | `/tasks/add` | Bearer | Celery addition demonstration (202) |
| GET | `/tasks/{uuid}` | Bearer | Generic addition-task result |

Common errors: 401 invalid/expired authentication, 404 missing/unowned resource,
409 registration/idempotency/cash/holding conflict, 422 invalid input or sub-$1
trade, and 503 provider/queue/configuration unavailability. Database commit
failures can return 500. For example, unauthenticated `/portfolio/me` returns
`{"detail":"Invalid or missing authentication credentials"}`. Invalid request
bodies return FastAPI's structured validation details. A saved simulation can
still return 201 when Redis is down: its durable record is recovered later.

## Run tests

Tests use a real, separate PostgreSQL database named **larp_finance_test**. They
apply migrations automatically, roll back ordinary fixture changes, and clean up
committed records used in concurrency tests. They mock external HTTP/publication;
no provider keys or Redis server are required for pytest.

With Python 3.13 and uv installed, start a disposable test database on a different
host port (the password below is deliberately test-only):

```powershell
uv python install 3.13
uv sync --locked --dev
docker run --detach --name larp-finance-test-db --publish 127.0.0.1:55432:5432 --env POSTGRES_USER=postgres --env POSTGRES_PASSWORD=local-test-only --env POSTGRES_DB=larp_finance_test postgres:18
docker exec larp-finance-test-db pg_isready -U postgres -d larp_finance_test
```

Repeat `pg_isready` until ready. Run tests in this PowerShell session:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres:local-test-only@127.0.0.1:55432/larp_finance_test'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:JWT_SECRET_KEY = 'local-test-signing-key-only-not-for-running-the-application'
uv run pytest -q
```

Close this terminal before running the application locally, or remove those three
session variables to restore your `.env` configuration. The test container can be
stopped/restarted with `docker stop larp-finance-test-db` and `docker start larp-finance-test-db`; when finished,
`docker rm -f -v larp-finance-test-db` removes that disposable container and its test volume.
Do not point tests at the application database. A name guard rejects other names,
but does not prove a database with that name is safe to use.

GitHub Actions uses Python from `.python-version`, `uv sync --locked --dev`,
PostgreSQL 18, and a job-local test signing key. Pull requests need no account
secrets or live market-data API access. Compose itself uses PostgreSQL 17.

Additional integration checks use the running Compose services and clean up their
own temporary records (keep the main API in historical demo mode):

```powershell
Get-Content scripts/verify_async_integration.py | docker compose --env-file .env.docker exec -T worker python -u -
Get-Content scripts/verify_real_history_integration.py | docker compose --env-file .env.docker exec -T worker python -u -
```

The first exercises the actual HTTP API, Celery and recovery scanner. The second
runs an authenticated in-process API and isolated Celery worker with actual Redis/
PostgreSQL; only external provider HTTP is mocked. It does **not** certify live
Twelve Data prices or account entitlements.

## Local development and limitations

For host development, copy `.env.example` to `.env` without replacing an existing
file, configure a reachable PostgreSQL/Redis instance, then run:

```powershell
uv sync --locked --dev
uv run alembic upgrade head
uv run python -m larp_finance.seed_assets
uv run uvicorn larp_finance.main:app --reload
```

Run `uv run python -m larp_finance.simulation_recovery` in another terminal and a
Linux/WSL Celery prefork worker with
`uv run celery -A larp_finance.celery_app:celery_app worker --loglevel=info --concurrency=2`.
Native Windows Celery solo does not provide the required hard time-limit behavior;
Compose is the recommended Windows setup. Compose's private service hostnames are
not host connection URLs; its database/Redis ports are intentionally not published.

This is a backend portfolio demonstration, not a production trading platform.
There is no frontend, real order execution, deposit/reset API, holdings listing,
dividend reinvestment, authentication rate limiting, token revocation, or dedicated
service-health endpoint. Generic addition-task results are UUID-based, without
per-user ownership records; use the owner-filtered simulation endpoint for financial
results. Spot caching is per-process; historical caching is shared. Recovery has
finite budgets and requires its scanner. Provider access, accuracy, quotas,
licenses and history depth remain external constraints. Real historical ranges
are capped at 4999 calendar days including padding.

The next phase is a comprehensive codebase audit. Further improvements should
follow that review, particularly authentication hardening, generic task ownership,
provider validation and integration coverage. Production hosting is out of scope.
