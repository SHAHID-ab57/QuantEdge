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
- Alembic (dependency only, migrations not yet wired)
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

| Variable | Required | Description | Default |
|---|---|---|---|
| `DATABASE_URL` | No* | Async PostgreSQL connection string | — |
| `DB_URL` | No* | Repo-convention alias for `DATABASE_URL` | — |
| `DB_POOL_SIZE` | No | Connection pool size | `5` |
| `DB_MAX_OVERFLOW` | No | Pool overflow connections | `10` |
| `DB_ECHO` | No | Log all SQL statements | `false` |

\* At least one of `DATABASE_URL` / `DB_URL` must be set for the database
layer to activate. `DATABASE_URL` takes precedence when both are present.

Example connection string:

```
postgresql+asyncpg://research:research@localhost:5432/eth_platform
```

Settings are loaded from environment variables and an optional `.env` file
(see `.env.example`; `.env` itself is git-ignored and never committed).
See `configs/environment.example.md` for the repo-wide variable catalog.

### Migrations

Alembic is declared as a dependency but **not yet wired**. When migration
support lands, the workflow will be:

```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

Until then, no tables are created by this service.

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

## Test

```bash
uv run pytest
```

Tests run without a database: `tests/conftest.py` forces an empty
`DATABASE_URL`, so the health endpoints deterministically exercise the
503/degraded path. Integration tests against a live PostgreSQL can be added
later behind the same fixture override.

## Directory Structure

```
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
│   ├── models/              # ORM models (placeholder)
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business services (placeholder)
│   ├── repositories/        # Data access layer (placeholder)
│   ├── dependencies/        # FastAPI dependencies (placeholder)
│   ├── middleware/          # Custom middleware (placeholder)
│   └── utils/               # Utility helpers
├── tests/                   # Test suite
├── pyproject.toml           # Project metadata and dependencies
├── .env.example             # Environment variable template
└── README.md
```

## Future Expansion

- Authentication and authorization.
- ORM models and Alembic migrations.
- Redis integration.
- External market data providers.
- Feature engineering and prediction endpoints.
- Background workers for data collection and model training.

No business logic is implemented in this scaffold; the infrastructure is
ready to grow module by module.