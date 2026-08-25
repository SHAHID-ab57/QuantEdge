# Testing

This document describes the backend test suite: how it is organized, how
to run it, and how to write tests that fit the conventions.

## Quick start

> **Note:** `pytest` is not installed globally — it lives inside the
> uv-managed virtual environment (`.venv`). A bare `pytest` fails with
> "command not found". Use one of:
>
> ```bash
> uv run pytest                    # recommended
> make test                        # Makefile wrapper
> source .venv/bin/activate        # or activate the venv first,
> pytest --cov                     # then `pytest` works directly
> ```

```bash
make test               # default suite: fast, no external dependencies
make test-verbose       # same suite with -v
make test-coverage      # coverage (terminal + HTML + XML), enforces the 80% gate
make test-integration   # adds tests that hit real external APIs
make test-performance   # adds timing-budget tests
make test-postgres      # runs only the PostgreSQL-backed tests
```

The default suite must stay green without Docker, a database, or network
access. Everything else is opt-in via markers.

## Directory structure

```text
tests/
├── conftest.py          # shared fixtures, flags, env isolation
├── helpers/             # reusable test utilities (never collected)
│   ├── factories.py     # DB-backed builders (exchange/market/candles)
│   ├── generators.py    # seeded deterministic random data
│   └── assertions.py    # response-shape assertions
├── api/                 # HTTP-level tests (FastAPI via httpx/ASGI)
├── features/            # Feature Engineering engine (see below)
├── repository/          # repository tests against in-memory SQLite
├── service/             # service-layer tests
├── websocket/           # generic WS connection machinery (scripted server)
├── event_bus/           # EventBus tests
├── processing/          # market data pipeline tests
├── state_manager/       # market state manager tests
├── unit/                # pure-logic tests, no DB/network
│   ├── core/            # settings, exception mapping
│   ├── db/              # engine/session lifecycle
│   ├── delta/           # Delta client, config, WS models
│   ├── marketdata/      # metrics, models, normalizer
│   ├── models/          # ORM base classes
│   ├── runtime/         # runtime composition root
│   ├── state/           # state snapshot models
│   └── ws/              # WS settings
├── integration/delta/   # real external APIs (marked `integration`)
└── performance/         # timing budgets (marked `performance`)
```

### Where does a test go?

| What you are testing                              | Directory        |
| ------------------------------------------------- | ---------------- |
| A single function/class in isolation              | `unit/...`       |
| One endpoint, full HTTP stack (app + DB override) | `api/`           |
| SQL/repository behavior                           | `repository/`    |
| Service orchestration with real repositories      | `service/`       |
| WS connection/reconnect/subscription logic        | `websocket/`     |
| Event bus routing/handling                        | `event_bus/`     |
| Pipeline stages (parse → normalize → validate)    | `processing/`    |
| Market state updates/snapshots                    | `state_manager/` |
| Real external API or real database                | `integration/`   |
| Throughput/timing budgets                         | `performance/`   |

Tests are named `test_*.py` and test functions `test_*`. Helper modules
that must not be collected do not start with `test_` and live in
`tests/helpers/` (e.g. `tests/websocket/server.py`).

## Running tests

| Command                                                                                | What it runs                                       |
| -------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `uv run pytest`                                                                        | default suite (skips `integration`, `performance`) |
| `uv run pytest -v`                                                                     | verbose output                                     |
| `uv run pytest -k "candle"`                                                            | filter by keyword                                  |
| `uv run pytest --run-integration`                                                      | adds tests hitting real APIs                       |
| `uv run pytest --run-performance`                                                      | adds timing-budget tests                           |
| `uv run pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml` | coverage, 80% gate                                 |
| `uv run pytest -m postgres`                                                            | only PostgreSQL-backed tests                       |

Coverage reports are written to `htmlcov/` and `coverage.xml`. The
`[tool.coverage.report]` block in `pyproject.toml` enforces
`fail_under = 80` and excludes `app/main.py` (a two-line entrypoint) and
`__main__` guards.

## Fixtures

The root `tests/conftest.py` provides the shared fixtures:

- `engine` / `session_factory` — in-memory SQLite engine with the full
  schema (StaticPool, one shared connection). The default for repository,
  service, and API tests.
- `db_session` — an open session for a test.
- `app` — a fresh FastAPI app with the `get_db` dependency overridden to
  the test engine.
- `client` — an async `httpx.AsyncClient` over the ASGI transport with
  lifespan managed (`asgi-lifespan`). Use `await client.get(...)`.
- `seeded`, `seeded_with_metadata`, `seeded_with_gap`, `seeded_varied`,
  `seeded_with_issues` — ready-made exchange/market/candle datasets.
- `trade_event`, `ticker_event`, `order_book_event` — canonical domain
  objects.
- `event_bus` — a fresh `EventBus`.
- `postgres_engine` / `pg_session_factory` — the opt-in PostgreSQL
  profile (see below).

Environment isolation: the conftest forces `DATABASE_URL=""` and
`DB_URL=""` **before any app import**, so the default suite never touches
a real database. Keep it that way — no test may rely on a configured
`DATABASE_URL` unless it is marked `integration`.

### Configuration files

There is no `pytest.ini`: all pytest configuration lives in
`pyproject.toml` under `[tool.pytest.ini_options]` (markers, warnings,
asyncio mode, test discovery). Coverage config lives in
`[tool.coverage.run]` / `[tool.coverage.report]`.

## PostgreSQL profile

The suite defaults to SQLite, but a PostgreSQL profile exists for tests
that must exercise real Postgres semantics:

- Set `TEST_DATABASE_URL` (default
  `postgresql+asyncpg://research:research@localhost:5432/eth_platform_test`),
  e.g. via the `infra/docker/docker-compose.yml` Postgres container.
- Mark the test `@pytest.mark.postgres` and request the
  `pg_session_factory` fixture.
- The fixture creates an isolated `test_<pid>` schema and drops it on
  teardown. When the database is unreachable, the test auto-skips with a
  clear message.

Run with `make test-postgres`.

## Markers

| Marker        | Meaning                                          | Enabled by          |
| ------------- | ------------------------------------------------ | ------------------- |
| `integration` | Hits real external APIs (Delta REST/WS, real DB) | `--run-integration` |
| `performance` | Timing budgets; correctness still asserted       | `--run-performance` |
| `postgres`    | Needs the PostgreSQL test database               | `-m postgres`       |

Markers are declared in `pyproject.toml` with `--strict-markers`, so
typos fail collection.

## Writing tests

1. Put the test in the directory that matches what it exercises (see the
   table above).
2. Prefer the shared fixtures over local copies. If you need a dataset,
   compose `seeded*` fixtures or the `tests/helpers/factories.py`
   builders; for randomized-but-deterministic data use
   `tests/helpers/generators.py` (fixed default seed — failures are
   reproducible).
3. Use the shared `client` fixture for HTTP tests; it is async, so test
   functions must be `async def`. `asyncio_mode = "auto"` means no
   `@pytest.mark.asyncio` decorator is needed.
4. Assert against response bodies with the `tests/helpers/assertions.py`
   helpers (`assert_domain_error`, `assert_pagination`, ...) when they
   fit.
5. Anything touching the network or a real database gets a marker — the
   default suite must run offline.
6. Timing budgets in `performance/` are deliberately generous
   (10–30 s): they catch catastrophic regressions, not machine noise.

## Feature Engineering tests

`tests/features/` covers the engine described in `ARCHITECTURE.md`
§ "Feature Engineering Engine", split by the guarantee each layer owns:

| File                         | Covers                                                                                                                                                                 |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_registry.py`           | Registration (class and instance), duplicate rejection, lookup, catalogue ordering, isolation, and (`TestDependencyValidation`) startup-time dependency/cycle checking |
| `test_pipeline.py`           | Parameter validation, warmup, alignment/uniqueness guarantees, error wrapping                                                                                          |
| `test_builtin_generators.py` | Each generator's maths, discovery, and the indicator-delegation contract                                                                                               |
| `test_dataset.py`            | Assembly, column collisions, warmup trimming, provenance, dataset ID/quality report, and (`TestPartialSuccess`) per-feature failure recording                          |
| `test_validation.py`         | Request-time dependency validation — a feature requested without its declared dependency is rejected, order-independent                                                |
| `test_export.py`             | CSV and JSON round-trip fidelity, provenance, dataset ID/export timestamp, and the quality summary                                                                     |
| `test_service.py`            | The candle-load join, row/limit semantics, preview truncation, export completeness, and one failing feature not blocking the others                                    |
| `test_ai_extensions.py`      | Pins the AI extension points' (`ai_extensions.py`) dataclass defaults and proves each Protocol is implementable                                                        |
| `test_performance.py`        | Opt-in (`--run-performance`) — builds a 100k-row, 5-feature dataset within budget; asserts the quality report's duplicate/missing-candle counting scales linearly      |

`tests/api/test_features_api.py` covers the same surface end to end over
ASGI, including the export endpoint's file-download headers and the
partial-success quality-report contract below.

Four conventions in these tests are worth keeping:

- **The registry and pipeline are tested against isolated, throwaway
  generators**, not the builtins. The pipeline's value is that every
  generator gets the same guarantees without implementing them, so the
  tests deliberately register misbehaving generators (misaligned output,
  duplicate columns, a raising `warmup()`) that no real generator would
  contain. `FeatureRegistry` is instantiable precisely so this cannot leak
  into the application catalogue. `test_registry.py`'s dependency-cycle
  tests follow the same convention with a second helper
  (`make_dependent_generator`) that declares `dependencies`, kept separate
  from the existing `make_generator` so it cannot disturb tests that don't
  care about dependencies.
- **The delegation contract is pinned, not assumed.**
  `test_sma_matches_the_indicator_engines_own_result` computes SMA through
  the indicator engine and through the feature pipeline and asserts they are
  identical. If someone ever reimplements the maths on the feature side,
  that test fails — which is the point, since the whole training/serving
  consistency guarantee rests on there being one implementation.
- **Error _status_ is asserted, not just the message** — for the errors
  that still hard-fail (`duplicate_feature_column`,
  `missing_feature_dependency`).
- **Partial-success is asserted by inspecting `quality.feature_failures`,
  not by expecting an exception.** An unknown feature, a bad parameter, an
  under-sized range, or an execution error in one requested feature must
  leave a dataset request at `200` with every other feature's columns
  intact — `test_dataset.py::TestPartialSuccess`,
  `test_service.py::test_one_failing_feature_does_not_block_the_others`,
  and `tests/api/test_features_api.py::TestDatasetErrors` all assert the
  failure by reading `dataset.quality.feature_failures[0]` /
  `body["quality"]["feature_failures"][0]`, never `pytest.raises`. This is
  a deliberate, tested behavior change from the engine's initial release
  (see `API.md` § "Feature engineering" for the exact before/after) and the
  tests were renamed to say so (e.g.
  `test_records_an_unknown_feature_as_a_quality_failure_not_a_404`).

## Gates

Before pushing, run:

```bash
uv run ruff check app tests scripts alembic
uvx pyright app tests
make test-coverage
```

All three must pass.
