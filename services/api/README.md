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

## Test

```bash
uv run pytest
```

Tests run without a database: `tests/conftest.py` forces an empty
`DATABASE_URL`, so the health endpoints deterministically exercise the
503/degraded path. Integration tests against a live PostgreSQL can be added
later behind the same fixture override.

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
- ORM models backed by Alembic migrations.
- Redis integration.
- Additional market data providers (beyond Delta Exchange).
- Market data ingestion from the Delta Exchange client.
- Feature engineering and prediction endpoints.
- Background workers for data collection and model training.

No business logic is implemented in this scaffold; the infrastructure is
ready to grow module by module.
