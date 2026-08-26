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
├── dataset_validation/  # Dataset Validation & Quality engine (see below)
├── experiments/         # Experiment Management repository/service tests
├── training/            # ML Training Framework tests (see below)
├── repository/          # repository tests against in-memory SQLite
│                        # (plus opt-in `postgres`-marked cascade tests)
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

## Dataset Validation tests

`tests/dataset_validation/` covers the engine described in
`ARCHITECTURE.md` § "Dataset Validation & Quality Engine" — a third
Strategy + Registry pattern on this platform, tested the same way the
first two (`tests/features/test_registry.py`,
`tests/unit/indicators/test_registry.py`) already are:

| File                         | Covers                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `conftest.py`                | `make_dataset(...)` — builds a `FeatureDataset` directly, without running the pipeline                                                                                               |
| `test_registry.py`           | Registration, duplicate rejection, lookup, catalogue ordering, isolated registries                                                                                                   |
| `test_engine.py`             | Rule execution, the pass/fail verdict, rule-subset selection, per-category summary seeding at zero                                                                                   |
| `test_rules_structural.py`   | `required_columns`, `data_types`                                                                                                                                                     |
| `test_rules_data_quality.py` | `missing_values`, `duplicate_rows`, `duplicate_timestamps`, `nan_values`, `infinite_values`                                                                                          |
| `test_rules_time_series.py`  | `timestamp_ordering`, `time_gaps`                                                                                                                                                    |
| `test_rules_feature.py`      | `metadata_consistency`, `feature_failures`                                                                                                                                           |
| `test_builtin_discovery.py`  | Every builtin rule module is auto-discovered, in its expected category, exactly once                                                                                                 |
| `test_service.py`            | `DatasetValidationService` delegates to `FeatureService.build_raw` and forwards `required_columns`/`rules` to the engine, via a stub in place of a real (DB-backed) `FeatureService` |

`tests/api/test_dataset_validation_api.py` covers the same surface end to
end over ASGI, against both a clean dataset (`seeded_varied`) and several
**intentionally corrupted** ones reused from the existing candle-quality
fixtures rather than newly invented: `seeded` (five candles with
byte-for-byte identical OHLCV — a real, not synthetic, duplicate-rows
scenario) and `seeded_with_gap` (a market whose candles skip the 03:00
bucket — a real gap for `time_gaps` to catch).

Three conventions worth keeping:

- **Rules are unit-tested against a hand-built `FeatureDataset`
  (`conftest.py`'s `make_dataset`), never a real pipeline run.** A rule's
  job is to check a dataset's _shape_; a hand-built one can express exactly
  the shape being tested (a duplicate timestamp, a NaN cell, a mismatched
  dtype, a feature failure) without needing a real generator that happens
  to produce it — the same "isolated, throwaway" convention
  `tests/features/test_registry.py` already established, applied to data
  instead of to generators.
- **The service test uses a stub, not a real `FeatureService`.**
  `DatasetValidationService` exists only to call
  `FeatureService.build_raw` and hand the result to the engine — proving
  that delegation doesn't require a database, so the test doesn't need one
  either. End-to-end coverage against a real (in-memory SQLite) database
  lives in the API test file instead.
- **Corrupted-data tests reuse existing fixtures over inventing new
  ones.** `seeded` and `seeded_with_gap` already exist for
  `candle_validation.py`'s own tests; reusing them here means the
  validation engine is proven against the same corrupted data the
  platform's other quality-reporting code is already tested against,
  rather than a second, parallel set of "bad data" fixtures that could
  drift from the first.

## Testing the ML Dataset Builder

`tests/ml_datasets/` covers the engine described in `ARCHITECTURE.md` §
"ML Dataset Builder" — a fourth Strategy + Registry (target generation),
tested the same way the first three already are, plus dedicated
composition and leakage-prevention tests:

| File                        | Covers                                                                                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `conftest.py`               | `candles(count, ...)` — ascending, monotonic synthetic OHLCV, one candle per hour                                                                               |
| `test_registry.py`          | Registration, duplicate rejection, lookup, catalogue ordering, isolated registries — mirrors `tests/features/test_registry.py`                                  |
| `test_pipeline.py`          | Parameter validation, horizon resolution, the forward-looking-contract check, alignment/uniqueness guarantees, error wrapping                                   |
| `test_targets.py`           | Each builtin target's maths (`next_close`, `next_return`'s zero-close guard, `next_direction`'s up/down/flat classification), and the contract-enforcement test |
| `test_split.py`             | Contiguity, ratio respect, chronological ordering, no reordering, `dataset_id` preservation across slices, ratio validation                                     |
| `test_dataset.py`           | Assembly, partial success, column collisions, the empty-dataset case, and (`TestLeakagePrevention`) the load-bearing no-look-ahead-bias tests                   |
| `test_builtin_discovery.py` | Every builtin target module is auto-discovered, exactly once, with its horizon parameter and output templates published                                         |
| `test_export.py`            | CSV/JSON round-trip fidelity, the `split` column, per-target provenance in the preamble/payload                                                                 |
| `test_service.py`           | The candle-load join (widened by warmup **and** horizon), row/limit semantics with re-splitting, export completeness                                            |

`tests/api/test_ml_datasets_api.py` covers the same surface end to end
over ASGI, including split-ratio validation, column-collision handling,
and a target-not-found request surfacing as a partial failure rather than
a 404 during a build.

**The leakage-prevention tests in `test_dataset.py::TestLeakagePrevention`
are the ones actually worth reading first.** They assert the property this
whole engine exists to guarantee, concretely rather than by inspection:

- `test_a_targets_value_always_comes_from_a_strictly_later_candle` builds a
  dataset, then for every surviving row independently re-derives what the
  target value _should_ be from the raw candle list and asserts equality —
  and separately asserts the target value is never equal to that same
  row's own close, so a copy-the-input bug would fail loudly rather than
  passing by coincidence.
- `test_trailing_rows_with_no_future_candle_are_never_present` asserts the
  very last candle can never appear as a row at all, since it has no future
  close to be labeled with.
- `test_a_multi_horizon_request_still_never_leaks` requests the same
  target at two different horizons in one build and independently verifies
  both columns, proving the realignment logic doesn't cross-contaminate
  when two target columns trim different numbers of trailing rows.

**The forward-looking contract is proven adversarially, not just by
inspection.** `test_targets.py::TestForwardLookingContractIsEnforced`
registers a deliberately cheating generator (`_Cheater`) that fabricates a
value for a row with no future candle, and asserts `TargetPipeline.run`
raises `TargetAlignmentError` rather than silently accepting the output —
the same "prove the guard actually fires" discipline
`test_sma_matches_the_indicator_engines_own_result` applies to the
training/serving-consistency guarantee.

**The empty-dataset case is deliberately engineered, not incidental.**
`test_dataset.py::TestEmptyDataset` builds `sma(period=8)` over 10 candles
(leaving only the last 2 rows past warmup) alongside `next_close(horizon=5)`
(undefined for the last 5) — both surviving rows fall inside the horizon
window, so `EmptyMLDatasetError` fires even though every target generated
successfully. The same test file separately proves that _zero target
columns_ (every target failed outright, not merely trimmed away) is a
valid, fully-explained result — mirroring the Feature Engineering Engine's
identical precedent for an all-failed feature request.

**Coverage-completing unit tests, called out so they aren't mistaken for
redundant.** A few branches need a synthetic, narrower test because the
realistic end-to-end path can't reach them: `test_service.py::TestCapRows`
calls the service's private `_cap_rows` directly on a synthetic 9-row
`MLDataset` capped to 3, since a real request's widen-then-cap arithmetic
can't be forced over the limit without also controlling the server's
configured maximum; `test_pipeline.py`'s `ZeroHorizon` generator and
`TestRegistryProperty` exist solely to exercise the `horizon == 0`
early-return branch and the pipeline's `registry` property, neither of
which any builtin target's `horizon >= 1` default reaches.

## Testing the Experiment Management System

`tests/experiments/` covers the engine described in `ARCHITECTURE.md` §
"Experiment Management System" — this platform's first genuinely
persistent, CRUD-backed domain, tested against the in-memory SQLite
database rather than isolated stubs, since there is no computation to
isolate from (unlike Feature/Target/Validation, there's no pluggable
registry here — a repository test _is_ the unit under test):

| File                 | Covers                                                                                                                                                                                                                                                           |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_repository.py` | CRUD (create/get/update/delete), tag replacement (add, remove, deduplicate), metrics/artifacts add+delete+cascade-on-delete, and search/filter/sort/pagination against real SQL                                                                                  |
| `test_service.py`    | Every domain error (`ExperimentNotFoundError`, `MetricNotFoundError`, `ArtifactNotFoundError`, `InvalidExperimentSortError`), partial updates (including clearing a nullable field and updating the JSON config columns), and summary-row metric/artifact counts |

`tests/api/test_experiments_api.py` covers the same surface end to end
over ASGI: every CRUD verb, nested metric/artifact create/delete,
search/filter/sort/pagination via real query parameters, the `422`s
Pydantic validation produces for a bad `status`/`artifact_type`/empty
`name`, and the unversioned-mount check every other domain's API test
file also includes.

**A real bug this suite caught, worth naming explicitly: `expire_on_commit
=False` does not mean "collections stay fresh after a commit."**
`ExperimentRepository.replace_tags` mutates the `experiment_tags` child
rows and commits, but the parent `Experiment.tags` collection already
loaded in the session's identity map is **not** automatically invalidated
by that commit (that's exactly what `expire_on_commit=False` opts out of).
The first version of `replace_tags` returned a stale, pre-mutation tag
list from `get_by_id` — a same-session identity-map hit short-circuited
the fresh `selectinload`. `test_replace_tags_adds_and_removes` caught this
immediately (asserting the _returned_ tags, not just the database's final
state). The fix is `self.session.expire(experiment, ["tags"])`
immediately after commit, forcing the next `get_by_id` to actually reload
the collection — documented in the repository's own docstring so it isn't
"fixed" back into the bug later.

**100% test coverage** on every new backend module
(`app/models/experiment.py`, `app/repositories/experiments.py`,
`app/services/experiments.py`, `app/schemas/experiments.py`,
`app/dependencies/experiments.py`, `app/api/v1/endpoints/experiments.py`).

## Testing the Machine Learning Training Framework

`tests/training/` covers the framework described in `ARCHITECTURE.md` §
"Machine Learning Training Framework", split by the same seam the code
itself draws between framework-free logic and database-backed
orchestration:

| File                          | Covers                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_state_machine.py`       | Every legal transition, every illegal transition (parametrized), and that every terminal status has no outgoing edge                                                                                                                                                                                                                                                                          |
| `test_registry.py`            | Register/get/duplicate-name/unknown-name on a throwaway `ModelAdapterRegistry`, plus that `load_builtin_model_adapters` registers `placeholder` and is idempotent                                                                                                                                                                                                                             |
| `test_placeholder_adapter.py` | `initialize`'s scalar-hyperparameter validation, and `train`'s determinism (same inputs → identical output; different `epochs` → different fabricated loss)                                                                                                                                                                                                                                   |
| `test_pipeline.py`            | Every one of the six stages runs in order (plain async stub hooks — no database), and every failure mode (missing dataset version, unknown adapter, `initialize`/`train` raising) stops at the right stage and never reaches `save_results`/`update_experiment`                                                                                                                               |
| `test_repository.py`          | CRUD, log append-and-order, and search/filter/sort/pagination against real SQL                                                                                                                                                                                                                                                                                                                |
| `test_service.py`             | Create/get/search/delete/cancel, a full successful `run()` (including that the linked experiment's status/metrics/artifacts are updated), a failed `run()` (missing dataset version, unknown adapter), the lifecycle guard against double-running or deleting a running job, and that a failed run's best-effort experiment update tolerates the experiment having been deleted independently |

`tests/api/test_training_api.py` covers the same surface end to end over
ASGI, including the model adapter catalogue endpoint and that `/run`
always returns `200` with the job's final state (never a `5xx`) even when
the pipeline fails. `tests/repository/test_training_postgres.py` (marked
`postgres`, mirrors `test_candles_postgres.py`'s opt-in pattern) is the one
place `ON DELETE CASCADE` on `training_jobs.experiment_id` and
`training_job_logs.job_id` is actually exercised — the in-memory SQLite
engine used everywhere else does not enable `PRAGMA foreign_keys`, so a
cascade-delete test written against it would pass or fail for the wrong
reason.

**A real gotcha this suite caught, worth naming: the same `expire_on_commit
=False` staleness `ExperimentRepository.replace_tags` already ran into,
here for a job's `logs` collection instead of an experiment's `tags`.**
`TrainingJobRepository.add_log` commits a new log row, but a `TrainingJob`
already loaded earlier in the same session keeps its stale (possibly
empty) `logs` collection in the identity map — `selectinload` only reloads
a relationship that isn't already populated. The fix is the identical one:
`self.session.expire(job, ["logs"])` right after the commit. A second,
related gotcha this introduced: any caller that logs _and then_ returns an
already-held job reference (rather than re-fetching) hands back a stale
collection — `TrainingJobService.cancel` was reordered to log first, then
re-fetch, so its response reflects the log line it just wrote.

**100% test coverage** on every new backend module (`app/models/
training.py`, `app/repositories/training.py`, `app/services/training.py`,
`app/schemas/training.py`, `app/dependencies/training.py`, `app/api/v1/
endpoints/training.py`, and every module under `app/training/`).

## Gates

Before pushing, run:

```bash
uv run ruff check app tests scripts alembic
uvx pyright app tests
make test-coverage
```

All three must pass.
