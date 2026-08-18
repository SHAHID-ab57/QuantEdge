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

Interactive API documentation (Swagger UI) is served at
<http://localhost:8000/docs> (ReDoc at <http://localhost:8000/redoc>).

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

## Market Data REST API

The API exposes validated historical candle data from the `candles` table.
It is read-only: no authentication, no WebSocket streaming, no trading.
Interactive docs (Swagger UI) at `http://localhost:8000/docs`.

### Endpoints

All endpoints are versioned under `/api/v1`.

| Method | Path                                  | Description                                                                    |
| ------ | ------------------------------------- | ------------------------------------------------------------------------------ |
| GET    | `/api/v1/markets`                     | All available markets, ordered by symbol.                                      |
| GET    | `/api/v1/markets/{symbol}/timeframes` | Timeframes that have stored candle data for the market (empty list when none). |
| GET    | `/api/v1/markets/{symbol}/candles`    | Page of candles for a timeframe, ascending by `open_time`.                     |
| GET    | `/api/v1/markets/{symbol}/latest`     | The candle with the newest `open_time` for a timeframe.                        |

### Query parameters (`/candles`)

| Parameter   | Type     | Required | Default | Description                                                                                                    |
| ----------- | -------- | -------- | ------- | -------------------------------------------------------------------------------------------------------------- |
| `timeframe` | string   | yes      | —       | Resolution, e.g. `1m`, `15m`, `1h`, `1d` (platform set: `1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 1w`).          |
| `start`     | datetime | no       | —       | Range start (inclusive), ISO-8601. Naive values are treated as UTC.                                            |
| `end`       | datetime | no       | —       | Range end (exclusive), ISO-8601. Must be after `start`; `start` and `end` are provided together or not at all. |
| `limit`     | integer  | no       | 100     | Max candles per page (1–1000, configured via `CANDLES_MAX_LIMIT`).                                             |
| `offset`    | integer  | no       | 0       | Candles to skip (>= 0).                                                                                        |

`/latest` takes `timeframe` (required). `/timeframes` and `/latest` take the
symbol in the path.

### Pagination

`/candles` responses include a `pagination` object:

```json
{
  "total": 79,
  "returned": 10,
  "has_more": true,
  "limit": 10,
  "offset": 0
}
```

Walk pages by incrementing `offset` until `has_more` is `false`.

### Response format

Prices and volumes serialize as JSON strings (exact decimals, no float
corruption); timestamps are ISO-8601 UTC:

```json
{
  "open_time": "2026-08-14T00:00:00Z",
  "close_time": "2026-08-14T01:00:00Z",
  "open": "3050.5",
  "high": "3060",
  "low": "3040",
  "close": "3055.25",
  "volume": "120.5",
  "quote_volume": null,
  "trade_count": null,
  "source": "delta"
}
```

### Error codes

Domain errors use the `{"code": ..., "detail": ...}` shape; malformed query
values (e.g. a bad datetime, `limit=0`, `offset=-1`) return FastAPI's
standard 422 `validation_error` shape.

| Code                | Status | Meaning                                                                           |
| ------------------- | ------ | --------------------------------------------------------------------------------- |
| `market_not_found`  | 404    | The symbol does not exist in the `markets` table.                                 |
| `candle_not_found`  | 404    | No candles stored for the market/timeframe (`/latest`).                           |
| `invalid_timeframe` | 400    | Timeframe not in the supported set.                                               |
| `invalid_range`     | 400    | `start` without `end` (or vice versa), or `end <= start`.                         |
| `limit_exceeded`    | 400    | `limit` above the configured maximum (query validation also rejects it with 422). |

### curl examples

```bash
# All markets
curl http://localhost:8000/api/v1/markets

# Timeframes with data for ETHUSD
curl http://localhost:8000/api/v1/markets/ETHUSD/timeframes

# First 10 hourly candles
curl "http://localhost:8000/api/v1/markets/ETHUSD/candles?timeframe=1h&limit=10"

# Next page
curl "http://localhost:8000/api/v1/markets/ETHUSD/candles?timeframe=1h&limit=10&offset=10"

# Range filter (half-open: 00:00 inclusive, 04:00 exclusive)
curl "http://localhost:8000/api/v1/markets/ETHUSD/candles?timeframe=1h&start=2026-08-14T00:00:00Z&end=2026-08-14T04:00:00Z"

# Latest hourly candle
curl "http://localhost:8000/api/v1/markets/ETHUSD/latest?timeframe=1h"

# Error: unknown symbol
curl -i http://localhost:8000/api/v1/markets/NOPE/candles?timeframe=1h
```

### Architecture

Requests flow through the layered pipeline:

```text
Router (app/api/v1/endpoints/market_data.py)
  -> Service (app/services/market_data.py)     validation + DTOs + domain errors
  -> Repository (app/repositories/)            all SQL
  -> PostgreSQL (candles, markets)
```

Responses never expose ORM models; the OpenAPI schema documents parameters,
examples, and error responses for every endpoint.

## WebSocket Streaming

Live market data is consumed from the Delta Exchange WebSocket API. Delta
splits the feed across two endpoints ("pods"): **public channels** (market
data, no credentials) live on the public socket, **private channels**
(account data) live on the private socket with `key-auth`. The client
defaults to the public socket; pass `public=False` (or `--private`) for the
private socket.

| Socket  | URL                                        | Channels                                        | Auth       |
| ------- | ------------------------------------------ | ----------------------------------------------- | ---------- |
| Public  | `wss://public-socket.india.delta.exchange` | All public market data                          | None       |
| Private | `wss://socket.india.delta.exchange`        | `orders`, `positions`, `user_trades`, `margins` | `key-auth` |

Subscribing to a public channel on the private socket (or vice versa) is
rejected with `subscription forbidden on this channel. Use appropriate pod`.

### Architecture

```text
Delta WebSocket ──> ConnectionManager (app/ws)   reconnect, backoff, monitors
                         │
                         ▼
              DeltaWebSocketClient (app/integrations/delta/websocket)
                         │   heartbeat, ping/pong, resubscribe
                         │   (+ key-auth on the private socket)
                         ▼
              MessageParser (exact + wildcard type registry)
                         │
                         ▼
              EventDispatcher ──> your listener coroutines (WSEvent subclasses)
```

`app/ws/` is a protocol-agnostic layer (connection, dispatcher, parser,
subscriptions, settings); `app/integrations/delta/websocket/` implements the
Delta protocol on top of it.

### Environment variables

| Variable                   | Default                                    | Description                             |
| -------------------------- | ------------------------------------------ | --------------------------------------- |
| `DELTA_WS_URL`             | `wss://public-socket.india.delta.exchange` | Public WebSocket endpoint               |
| `DELTA_WS_PRIVATE_URL`     | `wss://socket.india.delta.exchange`        | Private WebSocket endpoint              |
| `DELTA_WS_RECONNECT_DELAY` | `2.0`                                      | Initial reconnect delay (seconds)       |
| `DELTA_WS_MAX_RETRIES`     | `0`                                        | Max reconnect attempts; `0` = unlimited |
| `DELTA_API_KEY`            | —                                          | Required for the private socket         |
| `DELTA_API_SECRET`         | —                                          | Required for the private socket         |

### CLI listener

```bash
# Ticker for a single symbol (public socket, no credentials needed)
uv run python scripts/ws_listener.py --channel ticker=BTCUSD

# Multiple channels, multiple symbols each
uv run python scripts/ws_listener.py \
  --channel ticker=BTCUSD,ETHUSD \
  --channel candlestick_1m=BTCUSD \
  --verbose

# Private channels: authenticate against the private socket
uv run python scripts/ws_listener.py --private --channel orders=all

# Stop after 30 seconds
uv run python scripts/ws_listener.py --channel trades=BTCUSD --duration 30
```

Channels: `ticker`, `ob_l1`, `ob_l2`, `ob_updates`, `trades`,
`candlestick_<resolution>` (e.g. `candlestick_1m`), `mark_price`,
`spot_price`, `spot_30mtwap_price`, `funding_rate`, `product_updates`,
`system_status` (all public, no auth). Private channels (`orders`,
`positions`, `user_trades`, `margins`) require `--private` with valid
credentials. Omit the symbol list to subscribe to a whole channel (e.g.
`--channel product_updates`). Symbols use the product symbol (`BTCUSD`),
`MARK:`-prefixed symbols for mark price, option chain codes like
`BTC-310326`, category names like `put_options`, index symbols like
`.DEXBTUSD`, or `all`. Events are typed in
`app/integrations/delta/websocket/models.py`.

### Connection lifecycle

1. Connect with `connect_timeout`; on failure wait `reconnect_delay`
   (capped at `max_backoff`), doubling each attempt.
2. On connect: `enable_heartbeat`. On the private socket, then `key-auth`
   (HMAC-SHA256 signature; missing credentials raise `AuthenticationError`).
3. Resubscribe all previously queued subscriptions (after successful auth
   on the private socket).
4. Server sends `heartbeat` every ~30s; if none arrives within
   `heartbeat_timeout` (35s default) the connection is treated as dead and
   reconnects. The client answers server `ping` frames with `pong`
   (`pong_timeout`).
5. `subscribe`/`unsubscribe` calls while disconnected are queued and sent on
   the next successful connection.

### Library usage

```python
from app.integrations.delta.websocket.client import get_delta_ws_client
from app.integrations.delta.websocket import models as events


async def on_ticker(event: events.TickerEvent) -> None:
    print(event.sy, event.ts, event.d)


async def main() -> None:
    client = get_delta_ws_client()          # public socket, no credentials
    client.add_listener("ticker", on_ticker)
    await client.subscribe("ticker", ["BTCUSD"])
    client.start()
    try:
        await asyncio.Future()  # run forever
    finally:
        await client.close()
```

For private channels, use `get_delta_ws_client(public=False)` and set
`DELTA_API_KEY` / `DELTA_API_SECRET`.

### Troubleshooting

- **"subscription forbidden on this channel. Use appropriate pod."** The
  channel is not served by the endpoint you connected to. Public channels
  require the public socket; private channels require the private socket
  with authentication.
- **Rate limits.** Delta allows 150 connections per 5 minutes per IP. On
  429/close, wait 5–10 minutes before retrying.
- **Inactivity.** The server drops connections idle for 60s; heartbeats
  keep the connection alive.
- **Auth failures.** Wrong API key, expired timestamp, or an IP not
  whitelisted produces an auth failure and the client reconnects (the
  auth error is logged; credentials are never logged).

## In-process Event Bus

An in-memory, broker-free publish/subscribe bus that decouples modules
(WebSocket ingestion, market data storage, feature engineering, AI
prediction, paper trading, risk engine, notifications). Events are routed
by `event_type` to registered async handlers. The abstraction is thin on
purpose so a broker-backed implementation (Kafka/RabbitMQ) can replace it
without touching producers or consumers.

### Architecture

```text
Producer ──publish(event)──> EventBus ──schedules a task per handler──> Handler
                                                                         │
                                                                         ▼
                                                          logs + error isolation
```

- **Event** (`app/events/event.py`): `event_id` (UUID), `event_type`
  (defaults to the class name), `timestamp` (UTC), `source`, `payload`
  (auto-populated wire body from the typed subclass fields).
- **EventBus** (`app/events/bus.py`): `subscribe`, `unsubscribe`,
  `unsubscribe_all`, `publish`, `drain`; per-type handler sets (duplicate
  registrations are no-ops).
- **Handlers**: plain `async (event) -> None` callables. `LoggingHandler`
  and `DebugHandler` in `app/events/handlers.py` are reference examples.
- **Example events** (`app/events/example_events.py`):
  `MarketTradeReceived`, `CandleClosed`, `OrderBookUpdated`.

### Event lifecycle

1. A producer creates an event (`MarketTradeReceived(source="delta.ws", ...)`);
   `event_type` and `payload` are filled automatically.
2. `await bus.publish(event)` schedules one task per matching handler and
   returns immediately — publishers never block on handler work.
3. Each handler task runs concurrently; a raising handler is logged via
   `logger.exception` and never affects the others.
4. Publish (with subscriber count) and per-handler completion (with
   execution time in ms) are logged at DEBUG; failures at ERROR.
5. `await bus.drain()` waits for all pending handler tasks — used by
   tests and application shutdown.

### Adding a new handler

```python
from app.events import EventBus

bus = EventBus()

async def persist_candle(event) -> None:  # your async handler
    ...

bus.subscribe("CandleClosed", persist_candle)
await bus.publish(CandleClosed(source="ingest", symbol="BTCUSD", ...))
```

### Future migration to Kafka/RabbitMQ

Producers and consumers keep the same API. Swap `EventBus` for a
broker-backed implementation of the same interface:

- `publish` → broker producer (payload as the wire body, `event_id` for
  idempotent consumption).
- `subscribe`/`unsubscribe` → consumer group membership (external
  cancellation or broker-managed groups replace in-process references).
- `drain` → flush/pending-message accounting on the broker client.
- Gains: process-spanning delivery, durability, replay, backpressure,
  and horizontal scaling. Costs: ordering guarantees and exactly-once
  semantics become broker concerns.

## Market Data Processing Pipeline

Converts raw Delta Exchange WebSocket messages into
exchange-independent domain models and publishes them on the event bus.
Nothing in the application outside `app/marketdata` ever sees a
Delta-specific JSON structure. No persistence, no Redis — the pipeline
is a pure transform layer.

### Architecture

```text
Raw message
    │
    ▼
Parser        app.integrations.delta.websocket.parser (raw JSON -> typed WSEvent)
    │
    ▼
Normalizer    DeltaNormalizer (WSEvent -> TradeEvent / TickerEvent / OrderBookEvent)
    │
    ▼
Validator     pydantic constraints (prices > 0, UTC timestamps, symbol format)
    │
    ▼
Domain event  exchange-independent model
    │
    ▼
Event Bus     TradeEventReceived / TickerUpdated / OrderBookUpdated
```

Each stage is independently testable (`tests/marketdata/`). The pipeline
is wired into a WebSocket client as a listener — no client changes
needed:

```python
from app.events import EventBus
from app.marketdata import MarketDataPipeline, DeltaNormalizer

pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=EventBus())
for message_type in ("trades", "ticker", "ob_l1", "ob_l2", "ob_updates"):
    client.add_listener(message_type, pipeline.handle)
```

`MarketDataPipeline.process_raw(raw)` runs the full chain from a raw
JSON frame (used by tests and replay tooling).

### Live demo

`scripts/marketdata_demo.py` streams the public socket through the whole
pipeline and prints metrics with a pass/fail verdict:

```bash
uv run python scripts/marketdata_demo.py --duration 15
uv run python scripts/marketdata_demo.py --symbols BTCUSD --channels trades,ticker,ob_l1
```

It uses only the public client API (`start`/`run`/`close`/`subscribe`/
`add_listener`) — no context manager, no client modifications.

### Supported message types

| Delta channel | Domain event (bus `event_type`) | Notes                                                             |
| ------------- | ------------------------------- | ----------------------------------------------------------------- |
| `trades`      | `TradeEventReceived`            | `side` is `"unknown"` (public feed carries no side)               |
| `ticker`      | `TickerUpdated`                 | one event per product in the `d` array                            |
| `ob_l1`       | `OrderBookUpdated`              | top of book, `kind="l1"`, always snapshot                         |
| `ob_l2`       | `OrderBookUpdated`              | top-15 levels, `kind="l2"`, always snapshot                       |
| `ob_updates`  | `OrderBookUpdated`              | `kind="full"`, `is_snapshot` from `action`, `sequence` from `seq` |

Control and system messages (`heartbeat`, `pong`, `key-auth`,
`subscriptions`, `system_status`, `product_updates`) are recognized and
ignored. Well-formed messages of unhandled types (`mark_price`,
`spot_price`, `candlestick_*`, private account channels, unknown
channels) are counted as `unsupported_messages` and dropped.

### Event lifecycle

1. A raw frame arrives; the parser rejects malformed JSON and missing
   required wire fields (logged, counted as a validation failure).
2. The normalizer maps the parsed message to one or more domain events.
3. Domain model construction validates prices, sizes, timestamps, and
   symbols; failures are logged with the offending field and dropped.
4. Valid events are wrapped and published on the bus
   (`TradeEventReceived`, `TickerUpdated`, `OrderBookUpdated`).
5. `bus.drain()` waits for handler completion (application shutdown,
   tests).

### Metrics

`app.marketdata.metrics.ProcessingMetrics` tracks `messages_received`,
`messages_normalized`, `validation_failures`, `unsupported_messages`,
`events_published`, and processing latency (samples + average ms).
`metrics.snapshot()` is the stable contract a future Prometheus exporter
or `/metrics` endpoint will render.

### Extending to a new exchange

Implement the `Normalizer` protocol for the new exchange and reuse the
pipeline unchanged:

- The parser stage is injected (`MarketDataPipeline(parser=...)`); the
  default is the Delta parser.
- Domain models, validation, bus events, and metrics are shared.
- Exchange-specific conversion (field names, timestamp units, symbol
  formats) stays inside the normalizer.

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
│   │   ├── delta/           # Delta REST client + WS protocol layer
│   │   │   └── websocket/   # Delta WS models, auth, parser, client
│   ├── models/              # ORM models (placeholder)
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business services
│   ├── repositories/        # Data access layer
│   ├── dependencies/        # FastAPI dependencies
│   ├── events/              # In-process async event bus
│   │   ├── event.py         # Event base (id, type, UTC timestamp, source, payload)
│   │   ├── bus.py           # EventBus: subscribe/unsubscribe/publish/drain
│   │   ├── handlers.py      # LoggingHandler, DebugHandler (reference)
│   │   └── example_events.py# CandleClosed (future candle pipeline example)
│   ├── marketdata/          # Market data processing pipeline
│   │   ├── models.py        # TradeEvent, TickerEvent, OrderBookEvent (domain models)
│   │   ├── normalizer.py    # Normalizer protocol + DeltaNormalizer
│   │   ├── bus_events.py    # TradeEventReceived, TickerUpdated, OrderBookUpdated
│   │   ├── pipeline.py      # MarketDataPipeline (parse -> normalize -> validate -> publish)
│   │   └── metrics.py       # ProcessingMetrics (counters + latency, Prometheus-ready)
│   ├── ws/                  # Protocol-agnostic WebSocket layer
│   │   ├── connection.py    # Reconnect, backoff, heartbeat/ping monitors
│   │   ├── parser.py        # Message -> WSEvent parsing registry
│   │   ├── dispatcher.py    # Listener dispatch (exact + "*" wildcard)
│   │   ├── subscriptions.py # Subscribe/unsubscribe state + resubscribe
│   │   └── config.py        # WebSocketSettings
│   ├── middleware/          # Custom middleware (placeholder)
│   └── utils/               # Utility helpers
├── scripts/                 # Operational scripts
│   ├── ws_listener.py       # WebSocket market data listener CLI
│   └── marketdata_demo.py   # Live pipeline demo (WS -> bus -> metrics)
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
- Additional market data providers (beyond Delta Exchange) — implement
  the `Normalizer` protocol to join the pipeline.
- Feature engineering and prediction endpoints.
- Background workers for data collection and model training.
- Prometheus exporter for `ProcessingMetrics.snapshot()`.

No business logic is implemented in this scaffold; the infrastructure is
ready to grow module by module.
