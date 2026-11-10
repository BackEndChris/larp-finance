# Asynchronous simulation operations (Commit 22)

Compose runs PostgreSQL, Redis, the API, a Linux prefork Celery worker and a
separate recovery scanner. Start with:

    docker compose --env-file .env.docker up --build -d

Compose defaults `LARP_SIMULATION_MODE=demo` for the API and worker. These
simulations use fictional prices of $100 at purchase and $120 at valuation.
Commit 23 adds `real` mode, persistent data-source labels and actual trading
dates. See [historical data operations](HISTORICAL_DATA.md) for configuration,
price policy, caching and licensing. Outside Compose select a mode explicitly;
an absent/unsupported mode prevents new API simulation creation. Existing jobs
always retain their saved data source, regardless of the current default mode.

For local operation apply `uv run alembic upgrade head`, run the API and a Linux
Celery prefork worker, and also run `uv run python -m larp_finance.simulation_recovery`.
The scanner needs DATABASE_URL and REDIS_URL and runs every 15 seconds, with up
to 50 rows per scan. Do not use Windows Celery solo for timeout guarantees.

The committed simulation row is also its durable dispatch record. Creation
commits before best-effort publication. Publication and dispatch metadata use a
row lock, so concurrent scanners skip a locked row. A crash or ambiguous publish
can cause duplicate messages; only one unexpired processing token may save a
result. No database transaction remains open during market-data calculation.

Pending jobs are republished after 60, 120, 180, 240 then 300 seconds. There are
at most 12 publication attempts and 3 processing claims per simulation. Expired running
jobs (including legacy rows with no lease) are reclaimed automatically. Exhausted
jobs become failed with a safe error message. Broker downtime can exhaust this
budget; restoring Redis does not automatically reopen terminal failures.

Workers have a 480-second soft limit and 540-second hard limit, below the
600-second lease. Both successful and failed writes check the token, running
status and PostgreSQL clock after locking. Results after lease expiration are
discarded even if no replacement worker has claimed the row. SQLAlchemy failures
roll back and escape to Celery without automatic retries; the scanner handles
uncertain commits and abandoned leases. Completed/failed rows are never queued
again. Permanent calculation exceptions fail immediately. Transient historical
provider errors schedule a durable delayed retry, with the same three-claim
budget. `retry_not_before` also prevents duplicate deliveries bypassing backoff.
Celery results are ignored;
GET /simulations/{id} is the authenticated source of status/results.

Monitor `docker compose --env-file .env.docker logs worker recovery` and query
simulation status through the API. Recovery requires the scanner to remain
running. Hard process termination is provided by Linux Celery prefork, while
lease fencing protects stored results for all callers. External providers use
explicit network timeouts.

Integration verification (creates and removes its own fictional test records):

    Get-Content scripts/verify_async_integration.py | docker compose --env-file .env.docker exec -T worker python -

This checks the authenticated API, actual Celery execution, an injected publication
failure followed by automatic recovery, expired leases, exhausted retries, and a
separate Celery worker with deliberately unsupported provider configuration.

