# API Service

Backend API service for the AI-powered Ethereum Market Analysis and
Probabilistic Prediction Platform.

## Technology

- Python 3.13+
- FastAPI
- Uvicorn
- Pydantic v2 (with pydantic-settings)
- SQLAlchemy 2.x (dependency only, not yet wired)
- Alembic (dependency only, not yet wired)
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

Expected response:

```json
{
  "status": "ok",
  "service": "api",
  "version": "0.1.0"
}
```

## Test

```bash
uv run pytest
```

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
│   ├── db/                  # Database wiring (placeholder)
│   ├── models/              # ORM models (placeholder)
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business services (placeholder)
│   ├── repositories/        # Data access layer (placeholder)
│   ├── dependencies/        # FastAPI dependencies (placeholder)
│   ├── middleware/          # Custom middleware (placeholder)
│   └── utils/               # Utility helpers
├── tests/                   # Test suite
├── pyproject.toml           # Project metadata and dependencies
└── README.md
```

## Future Expansion

- Authentication and authorization.
- Database models and Alembic migrations.
- Redis integration.
- External market data providers.
- Feature engineering and prediction endpoints.
- Background workers for data collection and model training.

No business logic is implemented in this scaffold; the structure is ready
to grow module by module.