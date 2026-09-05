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

| File                         | Covers                                                                                                                                                                                                                                                      |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_registry.py`           | Registration (class and instance), duplicate rejection, lookup, catalogue ordering, isolation, and (`TestDependencyValidation`) startup-time dependency/cycle checking                                                                                      |
| `test_pipeline.py`           | Parameter validation, warmup, alignment/uniqueness guarantees, error wrapping                                                                                                                                                                               |
| `test_builtin_generators.py` | Each generator's maths, discovery, and the indicator-delegation contract                                                                                                                                                                                    |
| `test_dataset.py`            | Assembly, column collisions, warmup trimming, provenance, dataset ID/quality report, and (`TestPartialSuccess`) per-feature failure recording                                                                                                               |
| `test_validation.py`         | Request-time dependency validation — a feature requested without its declared dependency is rejected, order-independent                                                                                                                                     |
| `test_export.py`             | CSV and JSON round-trip fidelity, provenance, dataset ID/export timestamp, and the quality summary                                                                                                                                                          |
| `test_service.py`            | The candle-load join, row/limit semantics, preview truncation, export completeness, and one failing feature not blocking the others                                                                                                                         |
| `test_ai_extensions.py`      | Pins the AI extension points' (`ai_extensions.py`) dataclass defaults and proves each Protocol is implementable                                                                                                                                             |
| `test_performance.py`        | Opt-in (`--run-performance`) — builds a 100k-row, 5-feature dataset within budget; asserts the quality report's duplicate/missing-candle counting scales linearly                                                                                           |
| `test_cache.py`              | `FeatureCache`/`FeatureCacheKey` — mirrors `tests/unit/indicators/test_cache.py` test-for-test (key equality/hashing, get/put/clear, hit/miss stats, bounded LRU eviction)                                                                                  |
| `test_correlation.py`        | `compute_correlation_matrix` — perfect/inverse correlation, the diagonal always `1.0`, a constant column returning `0.0` (never `NaN`), non-numeric columns excluded, empty result for fewer than two numeric columns, pairwise-complete-rows null handling |
| `test_statistics.py`         | `compute_dataset_statistics` — exact mean/min/max, population variance/std against a known worked example, null counting kept separate from the numeric stats, an all-null column not raising, per-column independence                                      |
| `test_lineage.py`            | `build_lineage_graph` — today's real edgeless graph, direct/transitive ancestors and descendants once a throwaway generator declares `dependencies`, topological order, and `FeatureDependencyCycleError` on an artificial cycle                            |

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

**Feature cache, correlation, statistics, and lineage** extend the tests
above without changing any of the four conventions just listed:

- `test_pipeline.py` gained a `Counting` generator (a class-level call
  counter — the "cache probe") and a `cached_pipeline` fixture wiring a real
  `FeatureCache` in, plus a new `TestCache` class asserting a first run
  misses and actually computes, an identical second call hits and skips
  recomputation, different params or different candle ranges never collide,
  and a cache hit still reports the generator's own metadata (warmup,
  description) correctly.
- `tests/api/test_features_api.py` gained `TestLineageEndpoint` (5 tests,
  including a route-ordering regression test proving `GET /features/lineage`
  is never captured by `GET /features/{feature}`'s path parameter),
  `TestCorrelationEndpoint` and `TestStatisticsEndpoint` (5 tests each, using
  the `seeded_varied` fixture's exact 10x-correlated open/volume columns),
  and `test_reports_provenance_metadata` now also asserts
  `cache_status in ("hit", "miss", "disabled")`.
- **The repeated-request cache-hit test is deliberately order-independent.**
  `get_feature_pipeline()` is `functools.lru_cache`'d for the whole pytest
  process, so its `FeatureCache` instance is shared across every test in the
  session — an earlier test building the identical `candle_shape`/`sma`
  combination over the same fixture can leave a matching entry in the cache
  before this test even runs. `test_an_identical_repeated_request_hits_the_
feature_cache` therefore only asserts the _second_ identical call reports
  `cache_status: "hit"`, never that the first is a "miss" — the exhaustive
  miss/hit semantics are already covered exactly by the isolated
  `cached_pipeline` fixture in `test_pipeline.py::TestCache` and
  `test_cache.py` above, which don't share process-wide state.

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

| File                          | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_state_machine.py`       | Every legal transition, every illegal transition (parametrized), and that every terminal status has no outgoing edge                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `test_registry.py`            | Register/get/duplicate-name/unknown-name on a throwaway `ModelAdapterRegistry`, plus that `load_builtin_model_adapters` registers `placeholder` and is idempotent                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `test_placeholder_adapter.py` | `initialize`'s scalar-hyperparameter validation, and `train`'s determinism (same inputs → identical output; different `epochs` → different fabricated loss)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `test_pipeline.py`            | Every one of the six stages runs in order (plain async stub hooks — no database), and every failure mode (missing dataset version, unknown adapter, `initialize`/`train` raising) stops at the right stage and never reaches `save_results`/`update_experiment`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `test_repository.py`          | CRUD, log append-and-order, and search/filter/sort/pagination against real SQL                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `test_service.py`             | Create/get/search/delete/cancel, a full successful `run()` (`start` + `execute_run` combined, including that the linked experiment's status/metrics/artifacts are updated), a failed `run()` (missing dataset version, unknown adapter), the lifecycle guard against double-running or deleting a running job, that a failed run's best-effort experiment update tolerates the experiment having been deleted independently, `start`/`execute_run` exercised separately — including `execute_run` called on a second, independent `TrainingJobService` instance (its own session) than the one `start` used, the exact shape the background task itself relies on — and __two genuinely concurrent `start()` calls on the same job via `asyncio.gather`** (not sequential), asserting exactly one wins and the other gets the same 409 a sequential duplicate does; this is the test that actually exercises `TrainingJobRepository.try_transition_to_running`'s atomic `UPDATE ... WHERE status = 'pending'` guard — a manual reproduction confirmed the pre-fix read-then-check-then-write let both calls win                                                                  |
| `test_background.py`          | The non-blocking `/run` seam itself (`app/dependencies/training.py`): the background task opens its own DB session and still reads/writes correctly after the session that called `start` has been explicitly closed; a pipeline failure marks the job `failed` (via `execute_run`'s own `except`); a crash _outside_ `execute_run` (a monkeypatched raise) is still caught by the background task's own outer `except` and marks the job `failed`; **a failure in the crash-recovery write itself** (`_mark_job_failed_after_crash`'s own `get_engine()` made to raise, not just the original crash) leaves the job exactly where the crash found it (`running`) without the background task raising a second, unhandled exception — this test caught a real bug: `get_engine()` was originally called _outside_ that function's own `try`, so it escaped uncaught through the outer `except` block already handling the first crash; `wait_for_in_flight_training_jobs` deterministically awaits a scheduled run with no sleep; `cancel_in_flight_training_jobs` cancels and untracks a still-running task, mirroring `CandleSyncScheduler.stop()`'s cancel-then-await pattern |

`tests/api/test_training_api.py` covers the same surface end to end over
ASGI, including the model adapter catalogue endpoint, that `/run` returns
`200` with status `running` **before** the pipeline has necessarily
finished (proven with an artificially slow pipeline — the response lands
well under the induced delay), that a second concurrent `/run` call on the
same job is rejected with `409` rather than double-executed, and that the
job still settles into `completed`/`failed` (never a `5xx`) once the
background task is deterministically awaited
(`wait_for_in_flight_training_jobs`, not a real sleep) — see
`run_and_wait`, the helper every other test in this file that needs a
job's _final_ state uses instead of reading `/run`'s own (now immediate)
response body. `tests/repository/test_training_postgres.py` (marked
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

## Testing the Baseline Model Framework

Covers `ARCHITECTURE.md` § "Baseline Model Framework" — the two real
scikit-learn adapters and the bridge that gives them real data. Split
between adapter-isolated unit tests (no database) and full real-data
end-to-end tests (in-memory SQLite, real candles seeded, a real `fit`).

| File                                     | Covers                                                                                                                                                                                                                                                                                                                                                                                                               |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_dataset_loader.py`                 | Target column resolution (default-to-first, explicit override, unknown override), numeric-feature-column filtering, the dtype-compatibility check (a regression adapter over a categorical target), an empty split, and an unexpectedly-undefined value — all built with a real `MLDatasetBuilder` over synthetic in-memory candles, no database                                                                     |
| `test_serialization.py`                  | `LocalDiskModelSerializer` save/load round-trips a fitted model, returns a `file://` URI, gives every save a unique URI, creates its directory if missing, and rejects a non-`file://` URI                                                                                                                                                                                                                           |
| `test_logistic_regression.py`            | `initialize`'s hyperparameter defaults, `train` on deterministic perfectly-separable data (exact accuracy/F1, confusion matrix, recorded hyperparameters), `predict` loading the just-saved model, and a scikit-learn `fit` failure wrapped as `TrainingExecutionError`                                                                                                                                              |
| `test_linear_regression.py`              | The regression counterpart — deterministic perfectly-linear data (near-zero MAE/RMSE, R²≈1, recorded coefficients/intercept), `predict`, and the same failure-wrapping test                                                                                                                                                                                                                                          |
| `test_placeholder_adapter.py` (extended) | Now also covers `predict` (a fabricated constant per row) and that its `metadata.model_kind`/`requires_real_data` are `"placeholder"`/`False`                                                                                                                                                                                                                                                                        |
| `test_service.py` (extended)             | End-to-end `run()` for both real adapters against seeded candles and a real feature/target-built experiment (real metrics, confusion matrix, `file://` artifact, real `ExperimentMetric` rows); every real-data failure path (missing symbol/timeframe, missing feature_set/target_config, incompatible target dtype); `predict()` (success, not-yet-completed, row-length mismatch, and the adapter itself raising) |

`tests/api/test_training_api.py` adds the same real-data create → run →
predict flow end to end over ASGI, plus the model adapter catalogue now
asserting `model_kind`/`requires_real_data` for all three registered
adapters. Real candles are seeded directly through `app.models.Candle`/
`Exchange`/`Market` (the same factories `tests/ml_datasets/` and
`tests/helpers/factories.py` already use) — a "wobbling" (not monotonic)
hourly price series, deliberately not increasing on every row like
`tests/ml_datasets/conftest.py`'s own `candles()` helper, so `next_direction`
has both `"up"` and `"down"` labels for a classifier to actually learn
from.

**100% test coverage** on every module under `app/training/`, including
the two new adapters, `dataset_loader.py`, and `serialization.py`.

## Testing the Model Evaluation & Benchmarking Engine

Covers `ARCHITECTURE.md` § "Model Evaluation & Benchmarking Engine" (and
its "Production-Readiness Pass" follow-up) — `app/evaluation/` (metrics,
registry, engine, benchmark comparison), `app/services/evaluation.py`,
`app/repositories/evaluation_benchmark_runs.py`, and
`app/models/evaluation_benchmark_run.py`. Every metric, the registry, and
the engine are tested framework/database-free; the service and API layers
add a real, seeded-database path.

| File                | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `test_metrics.py`   | Every builtin metric's `compute` in isolation — accuracy/precision/recall/F1 on known inputs, ROC-AUC's binary case (positive-class column) and multiclass case (weighted OVR), ROC-AUC's guard against being called directly without probabilities, MAE/MSE/RMSE (RMSE = √MSE)/R², and each metric's declared `higher_is_better`/`category`/`requires_probabilities`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `test_registry.py`  | `MetricRegistry` register/duplicate/not-found/`has`/`for_category`/`describe_all` (sorted)/`__len__`/`__iter__`, plus that every documented builtin metric name is actually registered                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `test_engine.py`    | `EvaluationEngine.evaluate` — an unknown `model_kind` returns an empty report; a metric requiring probabilities is skipped (not errored) when none are given and runs when they are; a metric that raises is recorded as skipped with its exception message rather than propagating; a good and a bad metric coexist in one report without one sinking the other                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `test_benchmark.py` | `compare` — the max-scoring candidate wins an unregistered (default `higher_is_better=True`) metric; the min-scoring candidate wins a registered `higher_is_better=False` metric; a metric present on only some candidates still gets a winner; every candidate is returned unchanged; an empty candidate list yields an empty result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `test_service.py`   | `EvaluationService.list_metrics`; `benchmark` — both error paths, comparing real seeded `TrainingJob` rows, narrowing by `experiment_ids` (including 4 experiments at once, confirming no hidden two-item assumption), excluding a metrics-less completed job, `model_kind="unknown"` for a deregistered `model_type`, every new `BenchmarkCandidate` field present when the job recorded them and absent/`None` when it didn't (`symbol`/`timeframe`/`feature_count`/`sample_count`/`model_artifact_url`/`report`); Benchmark History — a successful benchmark recorded automatically, reopening a run returning its exact persisted request/response, `dataset_version`/`target_column` list filters, `BenchmarkRunNotFoundError` on an unknown id (get and delete), `InvalidBenchmarkRunSortError` on a bad sort column, and a simulated history-persist failure not failing the benchmark itself (mirroring `MLDatasetService`'s own best-effort-persist test) |

`tests/api/test_evaluation_api.py` adds the same benchmark flow end to end
over ASGI: `GET /evaluation/metrics` (including the unversioned mount),
`POST /evaluation/benchmark`'s `no_benchmark_target`/`empty_benchmark`
error responses, comparing two (and, separately, three) real
`logistic_regression` jobs trained on seeded candles through to a real
response body (candidates now including `symbol`/`timeframe`/
`feature_count`/`sample_count`/`model_artifact_url`/`report`, plus
`best_by_metric`), and the full Benchmark History flow —
`GET /evaluation/history` listing a just-recorded run,
`GET /evaluation/history/{id}` reopening it, `DELETE /evaluation/history/{id}`
removing it (then 404 on a re-fetch), and 404s for both `GET`/`DELETE` on
an unknown id. `tests/training/test_logistic_regression.py`/
`test_linear_regression.py` and `tests/api/test_training_api.py`'s
`TestRealBaselineModels` were re-run after the adapter refactor to confirm
every previously recorded metric value is unchanged and `roc_auc` now
appears alongside them for a classifier.

**100% test coverage** on every module under `app/evaluation/`,
`app/services/evaluation.py`, `app/repositories/evaluation_benchmark_runs.py`,
and `app/models/evaluation_benchmark_run.py` — one pre-existing, deliberately
unreachable defensive branch in `app/evaluation/benchmark.py` remains the
sole line not hit (a metric name derived from the union of every
candidate's own keys can never fail to match at least one candidate; see
that module's own comment).

## Testing the Live Prediction Service

Covers `ARCHITECTURE.md` § "Live Prediction Service" — `app/prediction/`
(base, engine, registry, errors), `app/services/prediction.py`,
`app/repositories/predictions.py`, `app/models/prediction.py`, and
`app/schemas/prediction.py`. The engine is tested framework/database-free;
the service and API layers reuse `tests/training/test_service.py`'s own
real-candle/real-experiment fixtures end to end rather than a second copy
of them.

| File                               | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/prediction/test_engine.py`  | `resolve_horizon` (matches by exact name and by prefix when several targets are configured, `None` for no match/empty/missing `target_config`/an unparseable or absent horizon) and `PredictionEngine.assemble` (a classifier's probabilities produce a real confidence/probability map; a regressor — or any adapter without `predict_proba` — gets an explicit `None` confidence and an explained reason; an adversarial case with three classes proving `confidence` is the _predicted_ class's own probability, not just the first or last entry)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tests/prediction/test_service.py` | `PredictionService.run` end to end against real seeded candles: the reconstructed as-of and `feature_columns` match the real stored latest candle exactly; a classifier's probabilities sum to 1 and its confidence is in range; a regressor has a numeric prediction and no confidence; persistence + `get` reopening it; Prediction History filtering by training job/experiment/symbol; an **adversarial normalization test** proving two different `as_of` times on the same `normalize_features=True` job produce genuinely different probabilities (the one observable symptom a degenerate single-row-normalization bug would produce, since a single row's own z-score against itself is always exactly zero regardless of its real values); and every error path — unknown job, a job that hasn't completed, a job never trained on real data (`placeholder`), an unknown market, a market with zero candles, the experiment's `feature_set` cleared or changed to a different, mismatched set after training, and an unknown prediction id on `get` |
| `tests/api/test_prediction_api.py` | The same at the HTTP layer: a labeled classifier prediction, the unversioned mount, a regressor's no-confidence shape, 404 for an unknown training job, 409 for a not-yet-completed job, 409 for a job with no recorded `feature_columns` (`placeholder`, which _does_ record a fabricated `artifact_uri` — this is checked one step later than `prediction_not_available`), 404 for an unknown market, get/reopen, list + filter by training job, an empty-symbol filter, and an invalid sort column                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

**99.7% test coverage** on every module listed above — one line
(`app/services/prediction.py`'s `UndefinedFeatureValueError` raise) is a
deliberately unreachable defensive branch, the same "should never happen
given `drop_warmup=True`" guarantee `app/training/dataset_loader.py`'s own
identical `to_numeric` helper already carries uncovered for the identical
reason.

## Testing Prediction Grading

Covers `ARCHITECTURE.md` § "Prediction Grading" — `app/prediction/grading.py`,
`PredictionService.grade_pending`/`_grade_one`
(`app/services/prediction.py`), the new `list_ungraded`/`record_grading`
repository methods, and `app.services.grading_scheduler.PredictionGradingScheduler`.

| File                                       | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/prediction/test_grading.py`         | `grade_one` against real built-in target generators/metrics (never stubs): a correct and an incorrect classification, a larger horizon looking the right number of candles ahead, a regression error that is exactly `MaeMetric.compute`'s own output (and `is_correct` exactly `AccuracyMetric.compute`'s own output — proving reuse, not a hand-rolled `==`/`abs()`), an unknown `model_kind`, an unmatched target column, and that too few candles propagates `InsufficientTargetDataError` rather than silently grading wrong                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `tests/prediction/test_service.py`         | `TestGradePending`, against the same real-candle fixtures `PredictionService.run`'s own tests use: a gradeable prediction (an `as_of` well before the seeded series' end, so its target candle is already stored) graded correctly with `graded_at` set and `available_after` cleared; a prediction at the very latest candle left untouched (`not_yet_knowable`, not an error); a regressor graded with `error` set and `is_correct` left `null`; an already-graded prediction never reprocessed on a second pass; a `target_config` edited out from under a pending prediction leaving it untouched; one unexpected per-row failure (`_grade_one` monkeypatched to raise) counted as `failed` without stopping the rest of the pass; and a repeated failure across two consecutive passes (`caplog`-asserted) logging on _every_ pass, at `ERROR`, naming the prediction, stating the real consequence ("will remain ungraded and be retried on every future grading pass"), and carrying a full traceback — not a bare, easy-to-miss message |
| `tests/services/test_grading_scheduler.py` | The scheduler itself, mirroring `tests/services/test_candle_sync.py`'s own conventions (`get_engine` monkeypatched to the test's in-memory engine): start/stop/no-op-without-an-engine/starting-twice-is-idempotent, `run_grading_tick` actually grading a real seeded prediction, `run_grading_once`, and the background loop running at least one tick before stopping cleanly — 100% line coverage                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tests/api/test_prediction_api.py`         | `TestGradedResponseShape`: a fresh prediction's `GET` shows the pending fields (`actual_outcome`/`is_correct`/`error`/`graded_at` all `null`, `available_after` set); after calling `grade_pending` directly (grading has no HTTP trigger — see `docs/api/API.md` § "Live Prediction Service"), both `GET /predictions/{id}` and `GET /predictions` reflect the graded outcome identically                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

**A real bug this suite caught before it shipped**: SQLAlchemy's `JSON`
column defaults to `none_as_null=False`, so a Python `None` written to
`actual_outcome` was stored as the JSON literal `null`, not a SQL `NULL` —
`WHERE actual_outcome IS NULL` (every grading query's own "still pending"
filter) matched nothing, ever. `TestGradePending`'s very first test caught
this immediately (`attempted == 0` when it should have been `1`). Fixed by
declaring the column `JSON(none_as_null=True)`; migration `99d6a6e10268`
also carries a one-time, hand-written data-fix `UPDATE` for rows written
before the fix (verified against the real dev database — see
`ARCHITECTURE.md` § "Prediction Grading" for the full account, including
the Step 1 normalization-consistency verification this task performed
before writing any grading code).

## Testing the Backtesting Engine

Covers `ARCHITECTURE.md` § "Backtesting Engine" — `app/backtest/` (base,
engine, errors), `app/services/backtest.py`, `app/repositories/backtest_runs.py`,
`app/models/backtest_run.py`, `app/schemas/backtest.py`,
`app/dependencies/backtest.py`, and the `PredictionService.grade_now`/
`PredictionRepository.tag_backtest_run` additions this feature needed on
the existing Live Prediction Service. The engine (`plan_steps`/`aggregate`)
is tested framework/database-free; the service and API layers reuse
`tests/prediction/test_service.py`'s own real-candle/real-experiment
fixtures (`train_completed_job`, `build_prediction_service`) end to end
rather than a second copy of them.

| File                                | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/backtest/test_engine.py`     | `plan_steps`: an even-dividing range walked exactly, a range needing more steps than `max_steps` capped from the _end_ with the honest uncapped `requested_steps` still reported, a range that exactly fits `max_steps` reporting no truncation, a partial final step still counted whole (`ceil`, not floor), and an empty/backwards range rejected. `aggregate`: a hand-computed classification accuracy (3/4 correct, independently countable) and regression MAE (`7/3`, independently computable) against a small fixture set — not re-derived from the engine itself — `roc_auc` gracefully skipped when any row lacks probabilities, reconstructed and computed only when _every_ row has them, and an empty row set producing an empty report rather than an error                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tests/backtest/test_service.py`    | Both of this feature's own defining properties, each proven by a test rather than asserted: `TestReusesLivePredictionExactly` (a backtest step and a live call for the identical job/symbol/`as_of` produce field-for-field identical output) and `TestNoLookAhead` (deleting every candle strictly after a fixed `as_of` and repeating the identical `PredictionService.run` call produces a bit-for-bit identical response). Also: backtest predictions tagged and excluded from Prediction History's default view (`TestTaggingAndAggregation`), aggregate metrics populated for both a classifier and a regressor via the real `EvaluationEngine`, honest step-capping/truncation reporting, a mid-walk failure (`PredictionService.run` monkeypatched to fail on its 2nd call) finalizing the _whole_ run as `failed` with its own partial `completed_steps` recorded, every named domain error (`TrainingJobNotFoundError`, `LiveFeatureReconstructionNotSupportedError`, `InvalidBacktestStepError`, `InvalidBacktestRangeError`, `BacktestRunNotFoundError`, `InvalidBacktestSortError`), `TestConcurrentStart` (two genuinely concurrent, byte-identical `start()` calls each succeed as independent rows — unlike a training job, `/backtests/run` never acts on an existing shared id, so there is no race to close; `try_transition_to_running`'s own atomic guard is separately proven race-safe against the identical pre-existing row, the same kind of test training's own fix used, even though nothing in this feature's real call graph ever exercises it that way), `TestGradingBoundary` (a `CandleRepository.get_candles` spy proves grading's own read — a separate query from feature computation's — is bounded to exactly `horizon + 1` rows via `limit`/`end=None`, never reaching the ~38 real candles the seeded series stores beyond it), and `TestRangeAgainstAvailableData` (a range reaching past the seeded series' own latest candle is rejected with `BacktestRangeExceedsAvailableDataError` rather than silently degenerating into repeated snapshot predictions; a range ending exactly at the latest candle's own coverage is accepted, proving the boundary is inclusive, not off-by-one; plus `market_not_found`/`candle_not_found` now checked upfront) |
| `tests/backtest/test_background.py` | Mirrors `tests/training/test_background.py` exactly for the shared `app.services.background_tasks` seam: a background task reads/writes after the original request session closed, no-engine-configured returns without raising, a crash outside `execute_run` still marked `failed`, a failure in the crash-recovery write itself leaving the run `running` (not silently anything else), deterministic `wait_for_all`-based scheduling, and `cancel_all` cancelling and untracking a hanging task                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `tests/api/test_backtest_api.py`    | The same at the HTTP layer: a completed backtest with its aggregate metrics, the unversioned mount, the run endpoint returning before an artificially slow `PredictionService.run` would finish (mirroring `test_training_api.py`'s own identical proof for training jobs), honest truncation reporting over HTTP, 404 for an unknown training job, 400 for an empty range, 400 for a range reaching past the latest stored candle, get/reopen, list most-recent-first + filter by symbol, 400 for an invalid sort column, and the Prediction History drill-down (`GET /predictions?backtest_run_id=`) showing only that run's own predictions while the default view shows only the live one                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tests/prediction/test_service.py`  | `TestGradeNow` (new, additive to the existing Live Prediction Service suite): grades a knowable prediction immediately, returns `None` (not an error) for one not yet knowable, and raises `PredictionRunNotFoundError` for an unknown id — proving `grade_now` behaves identically to `grade_pending`'s own per-row handling, since both call the exact same private `_grade_one`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

**No-look-ahead is inherited, not re-implemented — verified by reading the
code, then proven adversarially.** `PredictionService.run`'s own candle
fetch (`app/services/prediction.py`) always ends at `end=reference_time +
interval` — half-open, the same convention
`app.services.market_query.normalize_range`/`FeatureService.build_raw`
already use platform-wide — which structurally excludes any candle
strictly after the requested `as_of`. The backtest walker
(`BacktestService.execute_run`) calls this method completely unmodified
once per planned step; it does not, and must not, add any code that could
reintroduce leakage (widening the candle fetch, or passing a later `as_of`
alongside an earlier one). `TestNoLookAhead` (above) is the adversarial
proof: deleting every candle after a fixed `as_of` and repeating the
identical call produces an unchanged response.

**Async execution is the exact same shared mechanism training jobs use, not
a second one.** `app/services/background_tasks.py` (extracted from
`app/dependencies/training.py` once this feature needed the identical
tracking primitives) is exercised directly by
`tests/backtest/test_background.py`'s `TestSchedulingAndWaiting`, and
`tests/training/test_background.py` continues to pass unchanged —
confirming the extraction broke nothing for the feature it was extracted
from.

## Testing Paper Trading

Covers `ARCHITECTURE.md` § "Paper Trading" — `app/paper_trading/`
(base, errors, pricing, and `monitor.py` — the stop-loss/take-profit
event-bus subscriber), `app/services/paper_trading.py`,
`app/services/paper_trading_strategy.py` (the automated strategy's own
periodic scheduler), `app/repositories/paper_trading.py` (including the
pre-trade risk limits' own atomic concurrency guard,
`try_apply_trade_effects`, reused a fourth time by the automated
strategy's own order-placement calls), `app/models/paper_trading.py`,
and `app/schemas/paper_trading.py`.
Pricing/slippage/fee is tested framework/database-free (well,
`resolve_current_price` does touch a real `CandleRepository`/
`MarketStateManager`, but neither is a service); the service and API
layers seed a real market/candles directly rather than a second
fixture-building helper. Every pre-existing fixture in
`tests/paper_trading/test_service.py` that predates the risk-limits
feature opens its account with wide-open (100%) risk limits via
`build_service`'s own defaults, so its numbers (chosen for fill/PnL
arithmetic, not for staying under a 10%/50%/20% ceiling) are unaffected —
the risk-limit tests below always override tight, realistic limits
explicitly per account instead.

| File                                                              | Covers                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/paper_trading/test_pricing.py`                             | `resolve_current_price`: ticker preferred over trade preferred over the latest stored candle's own close; a fresh fallback candle not marked stale, one older than `staleness_threshold` marked stale; `NoPriceAvailableError` when nothing at all exists. `apply_fill_model`: a buy fills higher and a sell fills lower than the quote by exactly the modeled slippage; fee scales exactly with `fee_bps` alone, independent of `slippage_bps` (proven as two separate, single-variable changes, not one combined change that would conflate the two — `fee_applied` is not purely linear in `fee_bps` when `slippage_bps` also moves, since fee is charged on notional, which already embeds slippage)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tests/paper_trading/test_service.py`                             | A buy/sell fill's exact slippage and fee (service-level, end to end); a fallback-priced fill marked as such (fresh and stale); an over-balance buy rejected with the account left completely untouched (not partially filled); a sell exceeding the held quantity — not just a sell against zero position — and a sell with no position at all, both rejected (no shorting); unknown account/market errors; `TestHandComputedPnl` — a fixture sequence (start $100,000; buy 10 @ $1000; mark-to-market at $1100; sell 10 @ $1100) matching every realized/unrealized figure by hand, including `balance == starting_balance + realized_pnl` once the position is fully closed; and `TestAverageCostBasisAcrossMultipleBuys` — two buys of the _same_ symbol at two genuinely different prices (10 @ $1000, then 10 @ $1200), proving `average_entry_price` blends to the real quantity-weighted $1100.55 (neither the first buy's $1000.5 nor the most recent buy's $1200.6 alone — indistinguishable with only one buy, which is why this is its own fixture), then a partial sell of 5 realizing exactly $987.50325 against that blended cost basis, with the remaining position keeping the same blended average afterward (a sell never moves it)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `tests/paper_trading/test_service.py` (risk limits)               | `TestPositionSizeLimit` — an order whose resulting position value exceeds `max_position_size_pct` of current balance is rejected, and left completely untouched; a companion order just under the limit succeeds. `TestExposureLimit` — a position bought cheap that has since become far more valuable (the market moved hard between the buy and the check) makes an otherwise-trivial second order in a _different_ symbol get rejected purely because total exposure is valued at _current_, not entry, prices — proof the check could not have used stale cost-basis numbers and still produce this result. `TestDrawdownHalt` — a trade that drops balance more than `max_drawdown_pct` below `peak_balance` halts the account _after_ completing (never blocking the trade that causes it); any further order is then rejected with `TradingHaltedError` regardless of its own size or direction. `TestResumeTrading` — `resume_trading` clears the halt _and_ resets `peak_balance` to the current balance (proven: without the reset, the next test's own valid order would immediately re-halt the account on completion, regardless of direction); a valid order then succeeds and the account stays un-halted afterward.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tests/paper_trading/test_service.py::TestConcurrentExposureRace` | The concurrency guarantee itself, verified empirically — not sequentially. Two independent `PaperTradingService` instances (each its own session, mirroring `tests/training/test_service.py::test_two_genuinely_concurrent_starts_reject_exactly_one`'s exact shape), racing two different symbols' buy orders on the _same_ account via real `asyncio.gather`, each individually well under `max_exposure_pct`, jointly well over it. Exactly one succeeds; the other is rejected with `MaxExposureExceededError` specifically (not some other, accidental failure mode) — proving the loser re-evaluated its check against the winner's already-committed position rather than proceeding on stale numbers. Stable across repeated runs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `tests/paper_trading/test_service.py` (SL/TP validation)          | `TestStopLossTakeProfitValidation` — a stop-loss at or above, or a take-profit at or below, the current price is rejected (`InvalidStopLossPriceError`/`InvalidTakeProfitPriceError`); a sell can never carry either field (rejected at the schema level); valid thresholds are set at order-open time; a later buy that omits both fields never clears an existing one; and the cross-validation gap — a take-profit set first while price is low, then a stop-loss set later, individually valid against the new (higher) current price but numerically above the earlier take-profit — is caught (`StopLossNotBelowTakeProfitError`), proving the vs-current-price check applies only to the field a request actually names while the cross-check always runs on the final merged pair. `TestUpdatePositionThresholds` — the dedicated endpoint's set-both, omit-one-field-leaves-it-unchanged, explicit-null-clears-it, and not-found (no open position in this symbol) paths.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tests/paper_trading/test_monitor.py`                             | `StopLossTakeProfitMonitor`, mirroring `tests/services/test_grading_scheduler.py`'s own `get_engine`-monkeypatch convention (no HTTP request behind a bus event). `TestStopLossTrigger`/`TestTakeProfitTrigger` — a stop-loss/take-profit each close the position automatically the instant a published ticker event crosses it, recorded as a second order with `trigger_reason` set and `side="sell"`. `TestTriggeredSlippageModel` — the triggered fill's exact wider-slippage arithmetic (`$1097.25` at `TRIGGERED_SLIPPAGE_BPS=25`, never the manual model's `$1099.45`). `TestConcurrentTriggeredAndManualClose` — the third occurrence of this project's atomic check-then-act guard (see below): a triggered auto-close racing a genuinely concurrent manual close of the same position, via real `asyncio.gather(bus.drain(), manual_close_task)`, results in exactly one closing order every time — the loser fails cleanly (`InsufficientPositionError` for a losing manual close; a quiet no-op for a losing trigger, proven by asserting the winner's own `trigger_reason` when the manual side wins). `TestGapThroughBothLevels` — the pathological `stop_loss_price >= take_profit_price` state (structurally unreachable through the public API; forced here by writing straight to the row, bypassing `_validate_thresholds` on purpose) still closes exactly once, deterministically as `"stop_loss"` — proving the monitor's defense-in-depth check order is real, executed code, not dead documentation.                                                                                                                                                                                                                                                                 |
| `tests/api/test_paper_trading_api.py`                             | The same at the HTTP layer (a real `Runtime` with a live ticker published onto its bus, mirroring `test_system_health.py`'s own convention for exercising `MarketStateManager` without a real Delta WebSocket connection): create/list/reopen an account, the unversioned mount, a realistic buy fill's exact numbers over HTTP, 400 for insufficient balance, 400 for a sell exceeding the held quantity, 404 for an unknown market, orders/positions/summary all populated after a fill, 400 for an unsupported order-history sort column, an account's real default risk limits (10%/50%/20%) on creation, 400 `max_position_size_exceeded` over HTTP, a full risk-summary → drawdown-halt → 400 `trading_halted` → resume → succeeds walkthrough via `GET .../risk` and `POST .../resume-trading`, and `PATCH .../strategy`/`GET .../strategy/decisions` over HTTP: a fresh account starts disabled with the platform's own default threshold/stop-loss, enabling with no job named 400s `strategy_missing_training_job`, enabling against a real completed job (`train_completed_job`) succeeds and echoes every field back, an unknown job 404s `training_job_not_found`, and a fresh account's decision log lists empty before any scheduler tick has ever run                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `tests/paper_trading/test_service.py::TestUpdateStrategyConfig`   | `update_strategy_config` in isolation: a new account starts disabled with the platform's own default 65%/5% threshold/stop-loss; enabling against a real completed job succeeds; enabling with no job named at all (`StrategyMissingTrainingJobError`), an unknown job id (`TrainingJobNotFoundError`, reused verbatim from `app.training.errors`, not duplicated), and a job with no recorded symbol — a `placeholder` job trained on no real market data at all (`StrategyTrainingJobMissingSymbolError`) — are each rejected; disabling never requires a training job, and leaves an already-set one in place rather than clearing it; a partial update touching only one field leaves every other field (including `enabled` itself) exactly as it was.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `tests/paper_trading/test_strategy_scheduler.py`                  | `PaperTradingStrategyScheduler` — mirrors `tests/services/test_grading_scheduler.py`'s own conventions (`get_engine` monkeypatched to the test engine) plus a stubbed `get_prediction_service` for every test that needs a specific, controlled prediction outcome rather than a real trained model's harder-to-predict one. A confident (`confidence=0.9`), above-threshold, `"up"` prediction against a flat position opens a buy, sized and logged correctly. A below-threshold prediction places no order but is still logged, its reason naming the threshold. Every automated buy's own `stop_loss_price` is present and matches the configured percentage below the order's own `raw_price` exactly. A confident `"down"` prediction while long closes the full held quantity; a halted account rejects that close exactly like a manual one would. `TestSharesExistingRiskLimits` — a tight `max_exposure_pct`, pre-filled by an ordinary _manual_ buy in a different symbol, rejects the automated buy with the identical `MaxExposureExceededError` a manual order would hit — proof the strategy shares the existing guard rather than a second, unguarded one. Disabling an account (`update_strategy_config(enabled=False)`) leaves it absent from the very next tick's own query — no further decisions are ever logged for it. Three ticks (below-threshold, opens, non-directional `"flat"` signal) produce exactly three logged decisions, one of each outcome — every cycle logged, acted on or not. `TestRealPredictionWiring` — no stubbing: a genuinely trained job's own recorded symbol, a real `PredictionService.run` call, exactly one logged decision either way. Scheduler start/stop/no-database-configured wiring, matching every other scheduler's own tests. |

**Concurrency guard, the same primitive as the training-job race, adapted.**
`PaperAccountRepository.try_apply_trade_effects` guards `place_order`'s
whole check-then-act sequence with one
`UPDATE ... WHERE balance = :expected AND trading_halted = :expected` —
the identical core idea `TrainingJobRepository.try_transition_to_running`
uses (a single conditional `UPDATE`, its matched-row-count telling the
caller whether its precondition still held), just keyed on "the row is
still what I last read" instead of one fixed status value, because this
feature's precondition depends on live prices and every other open
position, not a single column. A losing attempt never proceeds on stale
numbers — it re-reads the account and every open position and retries
(bounded at `paper_trading_max_order_attempts`, default 5) — which is
what makes `TestConcurrentExposureRace` above deterministic rather than a
timing-dependent coin flip.

**The same guard, a third time.** `PaperTradingService.trigger_close`
(the market-triggered stop-loss/take-profit close) reuses the identical
`try_apply_trade_effects` atomic `UPDATE`, so a triggered auto-close and
a concurrent manual close of the same position can never both succeed —
`TestConcurrentTriggeredAndManualClose` above proves it the same way
`TestConcurrentExposureRace` and the training-job's own
`test_two_genuinely_concurrent_starts_reject_exactly_one` do: real
`asyncio` concurrency, not a sequential call order, and an assertion on
_which_ failure mode the loser gets, not just that something failed.

**The same guard, a fourth time — proven, not just asserted, by
`TestSharesExistingRiskLimits`.** The automated strategy
(`PaperTradingStrategyScheduler`) calls the exact same
`PaperTradingService.place_order` a manual order does — never a second,
parallel fill path — so it inherits `try_apply_trade_effects` for free.
Rather than re-testing the atomic `UPDATE` itself again, this test proves
the inheritance is real: a tight `max_exposure_pct`, most of that budget
already spent by an ordinary manual buy, and the automated buy is
rejected by the identical `MaxExposureExceededError` a second manual
order would hit in the same situation.

**Verified live, against the real dev database, not only against the test
fixtures above**: a real `POST /paper-trading/accounts` followed by a real
`POST .../orders` for ETHUSD filled at raw price $2510.20 (the real
latest stored candle's own close — `market_data_live` is `false` in this
dev environment) and fill price $2511.4551 (exactly `$2510.20 × 1.0005`),
with `fee_applied` exactly 10bps of the resulting notional; a follow-up
over-balance buy and an over-quantity sell were both rejected with the
exact error codes the automated tests already assert. See
`ARCHITECTURE.md` § "Paper Trading" for the full numbers.

## Gates

Before pushing, run:

```bash
uv run ruff check app tests scripts alembic
uvx pyright app tests
make test-coverage
```

All three must pass.
