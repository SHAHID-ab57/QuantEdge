# API Service

Backend API service for the AI-powered Ethereum Market Analysis and
Probabilistic Prediction Platform.

## Technology

- Python 3.13+
- FastAPI
- Uvicorn
- Pydantic v2 (with pydantic-settings)
- SQLAlchemy 2.x (async, with asyncpg)
- PostgreSQL 17
- Alembic (async, wired for migrations)
- httpx (async HTTP client, powers the Delta Exchange integration)
- Redis client (dependency only, not yet wired)

Package management uses **uv**.

## Install

```bash
cd services/api
uv sync
```

This creates a virtual environment and installs the project with its
development dependencies.

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

The API is served at `http://localhost:8000`.

Interactive documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response (database reachable):

```json
{
  "status": "ok",
  "service": "api",
  "version": "0.1.0",
  "database": "connected"
}
```

If the database is unavailable, the endpoint returns `503 Service
Unavailable` with a `detail` describing the failure, and the service refuses
to start when connectivity cannot be verified at startup (fail fast).

## Database (PostgreSQL)

### Requirements

- PostgreSQL 17 (or any version supported by asyncpg).
- The easiest local setup is the repository's `infra/docker/docker-compose.yml`,
  which provisions a `postgres:17-alpine` container with health checks:

  ```bash
  cd infra/docker
  cp .env.example .env   # set POSTGRES_PASSWORD
  docker compose up -d postgres
  ```

  Defaults: user `research`, database `eth_platform`, port `5432`.

### Environment Variables

| Variable          | Required | Description                              | Default |
| ----------------- | -------- | ---------------------------------------- | ------- |
| `DATABASE_URL`    | No*      | Async PostgreSQL connection string       | —       |
| `DB_URL`          | No*      | Repo-convention alias for `DATABASE_URL` | —       |
| `DB_POOL_SIZE`    | No       | Connection pool size                     | `5`     |
| `DB_MAX_OVERFLOW` | No       | Pool overflow connections                | `10`    |
| `DB_ECHO`         | No       | Log all SQL statements                   | `false` |

\* At least one of `DATABASE_URL` / `DB_URL` must be set for the database
layer to activate. `DATABASE_URL` takes precedence when both are present.

Example connection string:

```text
postgresql+asyncpg://research:research@localhost:5432/eth_platform
```

Settings are loaded from environment variables and an optional `.env` file
(see `.env.example`; `.env` itself is git-ignored and never committed).
See `configs/environment.example.md` for the repo-wide variable catalog.

### Migrations

Alembic is configured for async PostgreSQL migrations. The environment
(`alembic/env.py`) resolves the connection URL from the application settings
(`DATABASE_URL` / `DB_URL`), uses `Base.metadata` from `app/db/base.py`, and
runs migrations on the async engine. All ORM models imported by
`app/models/__init__.py` are auto-discovered by `alembic revision
--autogenerate` — no per-model wiring is needed.

**Current schema:** the initial migration
`20260811_592cf2283d14_create_market_data_schema` creates three tables:

| Table       | Purpose        | Key constraints                                                                                                                                                        |
| ----------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `exchanges` | Trading venues | PK, unique `name`, unique `slug`                                                                                                                                       |
| `markets`   | Trading pairs  | PK, FK → exchanges (CASCADE), unique `(exchange_id, symbol)`                                                                                                           |
| `candles`   | OHLCV facts    | PK, FK → markets (CASCADE), unique `(market_id, timeframe, open_time)`, OHLC range + non-negativity checks, time-series index `(market_id, timeframe, open_time DESC)` |

Workflow (via `Makefile`, run from `services/api`):

```bash
# Create a migration from model changes, then REVIEW the generated file
make db-create-migration MESSAGE="add users table"
#   → uv run alembic revision --autogenerate -m "add users table"

# Apply all pending migrations
make db-upgrade
#   → uv run alembic upgrade head

# Roll back one migration (other forms: db-downgrade REV=<revision>)
make db-downgrade
#   → uv run alembic downgrade -1

# View the migration chain
make db-history
#   → uv run alembic history --verbose

# Show where the database currently is
make db-current
#   → uv run alembic current

# Mark an existing/external database as migrated without running SQL
make db-stamp REV=head
#   → uv run alembic stamp head
```

Directly:

```bash
uv run alembic upgrade <revision>   # specific revision
uv run alembic downgrade base       # undo everything
uv run alembic revision -m "manual" # handwritten revision, no autogenerate
```

Applying the initial migration to a fresh database:

```bash
uv run alembic upgrade head
uv run alembic current               # expect: 592cf2283d14 (head)
```

Safety notes:

- Always **review autogenerated revisions** before applying them; autogenerate
  can miss or misinfer changes (e.g. constraints, enums).
- **Never edit an applied revision** — create a new one instead.
- Back up the database before destructive downgrades (<base>).
- Offline SQL rendering is supported:
  `uv run alembic upgrade head --sql`.

The schema is created by the initial migration; subsequent model changes add
new revisions.

### How Database Sessions Work

- `app/db/engine.py` builds a lazily-created, pooled async engine
  (`create_async_engine` with `pool_pre_ping=True`, `future=True`) and
  exposes `probe_database()` for connectivity checks.
- `app/db/session.py` provides `get_db()`, a FastAPI dependency that yields
  an `AsyncSession` per request and always closes it when the request ends:

  ```python
  async def endpoint(session: AsyncSession = Depends(get_db)) -> ...: ...
  ```

  Callers are responsible for `await session.commit()`; uncommitted work
  is rolled back when the session closes.

- The application lifespan (in `app/application.py`) verifies connectivity
  with `SELECT 1` at startup and fails fast if the database is unreachable,
  and disposes the engine cleanly at shutdown.

## Delta Exchange Integration

An async REST client for the Delta Exchange API lives in
`app/integrations/delta/` and is wired into the existing configuration system.

### Configuration

| Variable                | Required    | Description                      | Default                            |
| ----------------------- | ----------- | -------------------------------- | ---------------------------------- |
| `DELTA_BASE_URL`        | No          | REST base URL                    | `https://api.india.delta.exchange` |
| `DELTA_API_KEY`         | Conditional | API key (authenticated calls)    | —                                  |
| `DELTA_API_SECRET`      | Conditional | API secret (authenticated calls) | —                                  |
| `DELTA_REQUEST_TIMEOUT` | No          | Request timeout in seconds       | `10`                               |

Public market-data endpoints need no credentials. For authenticated requests
set **both** `DELTA_API_KEY` and `DELTA_API_SECRET` — they are validated
together, and an inconsistent pair fails fast with a descriptive error.

### Usage

```python
from app.integrations.delta import get_delta_client

async with get_delta_client() as client:
    products = await client.get("/v2/products", params={"state": "live"})
```

- `client.get(path, params=..., response_model=...)` and
  `client.post(path, json_body=..., response_model=...)` perform requests;
  pass `response_model` to validate the envelope `result` into a Pydantic
  model (e.g. `response_model=list[SomeModel]`), or omit it to get the raw
  result.
- Set `auth=True` to sign the request with your credentials (Delta
  HMAC-SHA256 signature; public calls stay unsigned).
- Transient failures are retried with exponential backoff: HTTP 429 and 5xx
  for idempotent methods, plus transport errors for any method. `Retry-After`
  is honored on 429.
- Errors are typed: `AuthenticationError`, `RateLimitError`, `APIError`, and
  `NetworkError` — all subclass `DeltaError`.
- Use the client as an async context manager so pooled connections are always
  released (`aclose()` releases them directly).

### Extending the client

Add a Pydantic model per endpoint payload, then a thin wrapper method:

```python
from pydantic import BaseModel
from app.integrations.delta import DeltaClient


class Product(BaseModel):
    id: int
    symbol: str


async def list_products(client: DeltaClient) -> list[Product]:
    return await client.get(
        "/v2/products",
        params={"state": "live"},
        response_model=list[Product],
    )
```

### Testing

Tests mock HTTP with `httpx.MockTransport` — no network access or
credentials are needed:

```bash
uv run pytest tests/integrations/delta
```

Covered behaviors: successful validation, malformed bodies, error envelopes,
schema mismatches, rate limiting (retried and exhausted), server errors,
timeouts, connect failures, signed headers, missing credentials, and secret
redaction in logs.

### Historical candle ingestion

`app/services/candle_ingest.py` fetches historical OHLCV candles from the
public `GET /v2/history/candles` endpoint, validates and normalizes each
record, and persists them into the `candles` table.

#### Supported timeframes

Delta Exchange India documents the following resolutions (as of 2025-10-18,
`7d`/`30d`/`2w` were deprecated by Delta and are intentionally unsupported):

| Resolution | Meaning    |
| ---------- | ---------- |
| `1m`       | 1 minute   |
| `3m`       | 3 minutes  |
| `5m`       | 5 minutes  |
| `15m`      | 15 minutes |
| `30m`      | 30 minutes |
| `1h`       | 1 hour     |
| `2h`       | 2 hours    |
| `4h`       | 4 hours    |
| `6h`       | 6 hours    |
| `1d`       | 1 day      |

#### Ingestion command

```bash
uv run python scripts/ingest_candles.py \
  --symbol ETHUSDT \
  --timeframe 1h \
  --start 2026-01-01 \
  --end 2026-01-31
```

- `--symbol` — the Delta market symbol exactly as stored in `markets`
  (synced by `scripts/sync_markets.py`; the initial use case is `ETHUSDT`).
- `--timeframe` — one of the supported resolutions above.
- `--start` / `--end` — `YYYY-MM-DD` (midnight UTC) or an ISO datetime;
  the range is half-open `[start, end)`.
- `--max-candles-per-request` — default `2000`, the documented Delta limit.

The market must already exist in the database (run the market sync first);
ingestion fails with guidance otherwise.

#### Historical range behavior

Delta returns up to 2000 candles per request and delivers them **newest
first**. The service:

- splits ranges longer than one request into contiguous, non-overlapping
  windows, one API request per window;
- sorts every fetched batch chronologically before validation;
- persists the whole run in a single transaction, so a failed request
  persists nothing (re-run the command — it is idempotent).

#### Validation rules

Each record is validated before persistence; invalid records are **logged
and rejected** (never silently fixed or inserted):

- timestamp is a non-negative Unix seconds value inside `[start, end)`;
- bucket-aligned open time (`time % duration == 0`);
- bucket already closed (`open_time + duration <= now`);
- `high >= max(open, close)` and `low <= min(open, close)`;
- `high >= low`, all prices non-negative;
- `volume >= 0`.

Timestamps are stored as timezone-aware UTC; prices and volume are stored as
`NUMERIC(38, 18)` decimals (no float corruption). Delta candles carry no
quote volume or trade count — those columns are `NULL` for ingested candles.

#### Duplicate handling

`(market_id, timeframe, open_time)` is unique. Re-running the same range
skips candles already stored (`duplicates_skipped` in the report) and never
inserts twice; the unique constraint is the backstop. Rows that still fail
at the database level (e.g. a concurrent ingest) are isolated, logged, and
counted as rejected.

#### Troubleshooting

| Symptom                          | Cause / fix                                                                      |
| -------------------------------- | -------------------------------------------------------------------------------- |
| `Market 'X' not found ...`       | Run `uv run python scripts/sync_markets.py` first.                               |
| `Unsupported timeframe`          | `7d`/`30d`/`2w` were deprecated by Delta; use a supported resolution.            |
| `Database is not configured`     | Set `DATABASE_URL` (or `DB_URL`) — see Environment Variables above.              |
| HTTP 429 / rate limit errors     | The client retries automatically with backoff; lower concurrency or retry later. |
| `table "candles" does not exist` | Run `make db-upgrade` to apply migrations.                                       |

#### Real API integration test

`tests/manual/test_real_candle_ingest.py` calls the live Delta API and
writes into the configured database. It is opt-in and never runs in the
normal suite:

```bash
uv run pytest tests/manual -m integration --run-integration -v
```

Optional environment overrides: `DELTA_INTEGRATION_SYMBOL` (default
`ETHUSD` — Delta India has no `ETHUSDT` product), `DELTA_INTEGRATION_TIMEFRAME`
(default `1h`), `DELTA_INTEGRATION_DAYS` (default `3`). The test ingests the
recent range twice and asserts the second run inserts nothing.

### Market data quality validation

`scripts/validate_market_data.py` is a **read-only** framework that checks
the integrity of stored OHLCV candles before they are consumed by APIs,
feature engineering, or AI models. It never writes to the database.

```bash
uv run python scripts/validate_market_data.py --symbol ETHUSD --timeframe 1h
```

Optional range (when omitted, the observed span of stored candles is
validated — from the oldest stored candle to the newest plus one bucket):

```bash
uv run python scripts/validate_market_data.py \
  --symbol ETHUSD \
  --timeframe 1h \
  --start 2026-01-01 \
  --end 2026-01-31
```

#### Validation rules

| Rule                                | Description                                                                                                                                                                                                                           |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OHLC dominance                      | `high >= open`, `high >= close`, `low <= open`, `low <= close`, `high >= low`.                                                                                                                                                        |
| Non-negative volume                 | `volume >= 0` and `quote_volume >= 0` when present.                                                                                                                                                                                   |
| Bucket alignment                    | `open_time` must fall on a timeframe bucket boundary (Unix epoch is the alignment origin).                                                                                                                                            |
| Close time consistency              | `close_time == open_time + timeframe duration`.                                                                                                                                                                                       |
| UTC timestamps                      | Aware timestamps must have zero UTC offset; naive timestamps are treated as UTC.                                                                                                                                                      |
| Chronological ordering / no overlap | Each candle's `open_time` must be at least the previous candle's `close_time`.                                                                                                                                                        |
| Duplicates                          | Exact duplicates on `(market_id, timeframe, open_time)` are checked (defensive; the unique constraint normally prevents them). Multiple candles inside one bucket (e.g. `12:00` and `12:30` for 1h) are counted as duplicate buckets. |
| Missing candles (gaps)              | Every bucket start in the validated range is expected; absent bucket starts are reported.                                                                                                                                             |

#### Quality score

The report includes two sub-metrics and one overall score (percentages):

```text
coverage = (expected - missing) / expected     # 0 when nothing is expected
validity = (total - invalid) / total           # 0 when no candles are stored
quality_score = 100 * coverage * validity
```

A perfect dataset scores 100; an empty one scores 0. Issue and missing
timestamp samples are capped (`--limit`, default 100) while counts stay
exact.

#### Common issues and how to fix them

| Symptom                                        | Cause / fix                                                                                                                                     |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Missing candles in the middle of history       | API outages or ingestion failures. Re-run `scripts/ingest_candles.py` for the affected range — ingestion is idempotent and fills only the gaps. |
| Missing candles at the leading edge            | History was never fetched. Determine the desired start and run `ingest_candles.py` with an earlier `--start`.                                   |
| `overlaps previous bucket` / duplicate buckets | Misaligned records entered through another path. Inspect the issue list and delete the offending rows (see below).                              |
| Invalid OHLC, negative volume                  | Corrupt rows in storage. Delete them and re-ingest the range from the exchange.                                                                 |

Deleting a single bad row (PostgreSQL):

```sql
DELETE FROM candles
WHERE market_id = (SELECT id FROM markets WHERE symbol = 'ETHUSD')
  AND timeframe = '1h'
  AND open_time = '2026-08-14 06:00:00+00';
```

Then re-run `scripts/ingest_candles.py` for the affected range to restore the
row from the exchange.

## Test

```bash
uv run pytest
```

Tests run without a database: `tests/conftest.py` forces an empty
`DATABASE_URL`, so the health endpoints deterministically exercise the
503/degraded path. Integration tests that call real external APIs are
marked `integration` and require `--run-integration`:

```bash
uv run pytest                                    # unit tests only
uv run pytest -m integration --run-integration   # real-API integration tests
```

## Directory Structure

```text
services/api/
├── app/
│   ├── main.py              # Application entry point
│   ├── application.py       # Application factory (create_app)
│   ├── api/                 # API routing
│   │   ├── router.py        # Router aggregation (/api/v1)
│   │   └── v1/
│   │       ├── router.py    # Version 1 router
│   │       └── endpoints/   # Version 1 endpoints
│   ├── core/                # Configuration, logging, exceptions
│   ├── db/                  # Database infrastructure
│   │   ├── engine.py        # Async engine, pooling, probe
│   │   ├── session.py       # Session factory and get_db() dependency
│   │   └── base.py          # Declarative base (for future models)
│   ├── integrations/        # External API clients (Delta Exchange)
│   ├── models/              # ORM models (placeholder)
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business services (placeholder)
│   ├── repositories/        # Data access layer (placeholder)
│   ├── dependencies/        # FastAPI dependencies (placeholder)
│   ├── middleware/          # Custom middleware (placeholder)
│   └── utils/               # Utility helpers
├── tests/                   # Test suite
├── alembic/                 # Migration environment and versions/
│   ├── env.py               # Async migration environment (app settings)
│   ├── script.py.mako       # Revision template
│   └── versions/            # Revision files (currently empty)
├── Makefile                 # Database task runner (db-* targets)
├── alembic.ini              # Alembic configuration
├── pyproject.toml           # Project metadata and dependencies
├── .env.example             # Environment variable template
└── README.md
```

## Future Expansion

- Authentication and authorization.
- Redis integration.
- Additional market data providers (beyond Delta Exchange).
- WebSocket streaming for live candles and tickers.
- Feature engineering and prediction endpoints.
- Background workers for data collection and model training.

No business logic is implemented in this scaffold; the infrastructure is
ready to grow module by module.
