# Project State — Evidence-Based Snapshot

**Produced**: 2026-08-31, by a direct code audit (not inferred from
documentation). Every claim below was checked by reading source files,
running greps for the exact symbol/route/table cited, or executing the
relevant test suite. Where a claim couldn't be verified either way, it is
listed in [§7 Open Questions](#7-open-questions) instead of guessed at.

This file is a **standalone snapshot**. It does not edit `ROADMAP.md`,
`CLAUDE.md`, `TASKBOOK.md`, or any other existing document — reconciling
those against this snapshot is a deliberate human decision, not something
done silently here.

---

## 1. Executive Summary

| Subsystem                                                                            | Rating                 | One-line reason                                                                                                                                                               |
| ------------------------------------------------------------------------------------ | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Market Data core (exchanges/markets/candles, ingestion, sync, validation)            | **VERIFIED**           | Real models/services/repositories, mounted API, 251 `tests/api` + repository tests passing.                                                                                   |
| Delta Exchange REST client                                                           | **PARTIAL**            | Candles fully real and tested; ticker/funding-rate/open-interest/mark-price have **no REST method at all** (mark_price/open_interest only arrive via WS).                     |
| Delta Exchange WebSocket client                                                      | **PARTIAL**            | Trades/order book/ticker genuinely live, reconnect+heartbeat real and tested; **candles are never streamed over WS** (channel registered in the parser but never subscribed). |
| Technical Indicator Engine + Chart Overlay                                           | **VERIFIED**           | Real registry/engine/cache backend + fully built frontend page and overlay system, tests passing.                                                                             |
| Feature Engineering Engine (+ 2 hardening passes)                                    | **VERIFIED**           | Real pipeline, versioning/lineage/correlation/cache/statistics all present in code, frontend page built, tests passing.                                                       |
| Dataset Validation & Quality Engine                                                  | **VERIFIED**           | Real rule engine + report + frontend page, tests passing.                                                                                                                     |
| ML Dataset Builder                                                                   | **VERIFIED**           | Real split/export/pipeline + Dataset History persistence + frontend page, tests passing.                                                                                      |
| Experiment Management System                                                         | **VERIFIED**           | Real CRUD + metrics/artifacts + now-editable feature_set/target_config/split_config, tests passing.                                                                           |
| ML Training Framework + Baseline Model Framework                                     | **VERIFIED**           | Two real scikit-learn adapters (logistic/linear regression) + placeholder adapter, real pipeline/state machine, tests passing.                                                |
| Model Evaluation & Benchmarking Engine                                               | **VERIFIED**           | Fully built end-to-end (engine, DB-persisted benchmark runs, 5 endpoints, frontend page) — **the codebase shows this complete, not "in progress."**                           |
| External data connectors (News, Etherscan, FRED, Fear & Greed, DefiLlama, CoinGecko) | **MISSING**            | Zero implementation for all six — env var placeholders only (some not even that), no client code anywhere.                                                                    |
| Redis (caching / pub-sub / queue)                                                    | **MISSING**            | Provisioned (docker-compose + dependency) but **zero call sites** — every reference in the code is a comment explaining it's deliberately unused.                             |
| Background jobs / task queue                                                         | **MISSING**            | No queue library; only an in-process `asyncio` polling loop (`CandleSyncScheduler`) and a synchronous, blocking training-job `run()`.                                         |
| Rate limiting                                                                        | **PARTIAL**            | Outbound: real retry/backoff on Delta 429/5xx. Inbound: none — this platform's own API has no rate limiting at all.                                                           |
| Authentication / Authorization                                                       | **MISSING**            | No auth on any route, confirmed both in code and in `docs/api/API.md`'s own "Authentication: None" section.                                                                   |
| CI/CD                                                                                | **MISSING**            | No `.github/` directory anywhere in the repo; all checks are local git hooks only.                                                                                            |
| Logging & monitoring                                                                 | **PARTIAL**            | Real but minimal: stdlib `logging.basicConfig`, no structured logging, no tracing, no metrics export, no error tracking.                                                      |
| Frontend dashboard shell + routes                                                    | **MIXED**              | 12 of 15 routes fully built and real; `dashboard`, `research`, `settings` are still literal placeholders.                                                                     |
| Backend test suite                                                                   | **VERIFIED (passing)** | 1406 tests collected, 0 failures, 0 errors, 18 skipped (opt-in), 97.30% coverage (gate 80%).                                                                                  |
| Frontend test suite                                                                  | **VERIFIED (passing)** | 1819 tests across 204 files, all passing; `tsc --noEmit` and `eslint` both clean.                                                                                             |

---

## 2. Capability Inventory

### 2.1 Market Data core

| #   | Claim                                                         | Status                             | Evidence                                                                                                                                                                                                 | Missing (if partial)    |
| --- | ------------------------------------------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| 1   | Exchange/Market/Candle relational model                       | VERIFIED                           | `app/models/exchange.py`, `app/models/market.py`, `app/models/candle.py`; migration `20260811_592cf2283d14_create_market_data_schema.py` applied.                                                        | —                       |
| 2   | Candle ingestion (idempotent historical fetch)                | VERIFIED                           | `app/services/candle_ingest.py` (confirmed present in `app/services/`); exercised by `tests/services/` and `tests/repository/`.                                                                          | —                       |
| 3   | Candle-sync scheduler (periodic catch-up)                     | VERIFIED, but not a real scheduler | `app/services/candle_sync.py:56` `class CandleSyncScheduler` — a plain `asyncio.Event().wait(timeout=self._interval_seconds)` loop inside the API process, not a separate worker.                        | See §4 Background Jobs. |
| 4   | Market-catalog sync from Delta                                | VERIFIED                           | `app/services/market_sync.py:31` `PRODUCTS_PATH = "/v2/products"`, real upsert logic.                                                                                                                    | —                       |
| 5   | Candle data-quality validation (gaps/duplicates/OHLC)         | VERIFIED                           | `app/services/candle_validation.py` (present per `CLAUDE.md`'s own file listing, confirmed on disk); read-only report generator.                                                                         | —                       |
| 6   | Read-only market data + system health/status/metrics REST API | VERIFIED                           | `app/api/v1/endpoints/market_data.py` (6 routes, `grep -c "@router\."` = 6), `app/api/v1/endpoints/health.py`, mounted at both `/api/v1/*` and `/*` (`app/api/v1/router.py`, `app/api/router.py:12-13`). | —                       |

### 2.2 Delta Exchange integration

| #   | Claim                                    | Status   | Evidence                                                                                                                                                                                                                                                                                                       | Missing (if partial)                                                           |
| --- | ---------------------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 7   | REST client — candles                    | VERIFIED | `app/integrations/delta/client.py:150` `get_candles()`, `CANDLES_PATH = "/v2/history/candles"` (`client.py:42`); tested in `tests/unit/delta/test_client.py` (16 test functions incl. rate-limit retry/exhaustion, auth, secret-redaction).                                                                    | —                                                                              |
| 8   | REST client — ticker                     | MISSING  | No REST path exists anywhere; `grep -rn "\"/v2/" app` only returns `/v2/products` and `/v2/history/candles`. Ticker data only ever arrives via the WebSocket `TickerEvent` (`app/marketdata/models.py:66`).                                                                                                    | A real `GET /v2/tickers` (or per-symbol) REST method.                          |
| 9   | REST client — funding rate               | MISSING  | No REST path. A `funding_rate` WS message _type_ is registered (`app/integrations/delta/websocket/parser.py:30`) but never subscribed to (see #11) — dead on both paths.                                                                                                                                       | Both a REST method and a live WS subscription.                                 |
| 10  | REST client — open interest              | MISSING  | No REST path. Only reachable as a sub-field of the WS `TickerEvent.open_interest` (`app/marketdata/models.py:76`), populated from the ticker payload (`app/marketdata/normalizer.py:166`).                                                                                                                     | A dedicated REST/WS open-interest source.                                      |
| 11  | REST client — mark price                 | MISSING  | No REST path. Same as #10 — `TickerEvent.mark_price` (`models.py:74`) via WS ticker only.                                                                                                                                                                                                                      | A dedicated REST mark-price source.                                            |
| 12  | WS client — trades                       | VERIFIED | Subscribed live: `LIVE_CHANNELS = ("trades", "ticker", "ob_l1", "ob_updates")` (`app/runtime.py:53`); normalized → `TradeEventReceived` → published to the event bus (`app/marketdata/pipeline.py:120,132`).                                                                                                   | —                                                                              |
| 13  | WS client — order book                   | VERIFIED | `ob_l1`/`ob_updates` in `LIVE_CHANNELS`; normalized → `OrderBookUpdated` (`pipeline.py:136`); also backs the Live Order Book Viewer per `FRONTEND.md:495-758`.                                                                                                                                                 | —                                                                              |
| 14  | WS client — candles                      | MISSING  | `"candlestick_*"`/`"candlesticks"` are registered in the parser (`parser.py:26-27`) so a message _could_ be parsed, but neither string appears in `LIVE_CHANNELS` — nothing ever subscribes, so no candle message is ever received this way. Candles reach the system only through REST ingestion/sync (#2–3). | A live subscription to `candlestick_*` and a normalizer/bus-event path for it. |
| 15  | WS reconnection with exponential backoff | VERIFIED | `app/ws/connection.py:3-4` (module docstring), real supervised reconnect loop; tested: `tests/unit/delta/test_ws_client.py:159` `test_reconnect_reauths_and_resubscribes`.                                                                                                                                     | —                                                                              |
| 16  | WS heartbeat/pong supervision            | VERIFIED | `app/ws/connection.py:82,88,116` (heartbeat event/state tracking); tested: `test_ws_client.py:144` `test_heartbeat_keeps_connection_alive`.                                                                                                                                                                    | —                                                                              |

### 2.3 External data connectors

| #   | Claim                                 | Status  | Evidence                                                                                                                                                                                                                  | Missing (if partial) |
| --- | ------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| 17  | Marketaux / NewsAPI news connector    | MISSING | `docs/architecture/SystemContext.md:69,88,136` documents it as a target external system. `MARKETAUX_API_KEY` is an unused placeholder in root `.env.example:30`. `grep -rln "marketaux" app` (services/api) → no matches. | Everything.          |
| 18  | Etherscan on-chain connector          | MISSING | `SystemContext.md:70,89,137`. `ETHERSCAN_API_KEY` placeholder only (`.env.example:31`). No code.                                                                                                                          | Everything.          |
| 19  | FRED macroeconomic connector          | MISSING | `SystemContext.md:71,90,138`. `FRED_API_KEY` placeholder only (`.env.example:32`). No code.                                                                                                                               | Everything.          |
| 20  | Alternative.me Fear & Greed connector | MISSING | `SystemContext.md:72,91,139`. Not even present as an env var placeholder. No code.                                                                                                                                        | Everything.          |
| 21  | DefiLlama connector                   | MISSING | `SystemContext.md:73,92,140`. `DEFILLAMA_BASE_URL` placeholder only (`.env.example:33`). No code.                                                                                                                         | Everything.          |
| 22  | CoinGecko connector                   | MISSING | `SystemContext.md:68,87,135` (not in the user's original 5-item list, found during this audit — see §3). `COINGECKO_API_KEY` placeholder only (`.env.example:29`). No code.                                               | Everything.          |

### 2.4 Technical Indicator Engine + Indicator Management & Chart Overlay

| #   | Claim                                                  | Status                           | Evidence                                                                                                                                                                                | Missing (if partial) |
| --- | ------------------------------------------------------ | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| 23  | Indicator registry/engine (backend)                    | VERIFIED                         | `app/indicators/{registry,engine,base,params,errors,cache}.py`; endpoints `app/api/v1/endpoints/indicators.py` (4 routes).                                                              | —                    |
| 24  | Indicator result cache                                 | VERIFIED (in-process, not Redis) | `app/indicators/cache.py:76` `class IndicatorCache`; real call sites: `app/dependencies/indicators.py:31`, `app/features/builtin/__init__.py:67`.                                       | —                    |
| 25  | Indicator Management & Chart Overlay System (frontend) | VERIFIED                         | `apps/dashboard/src/features/indicator-overlays/`, `src/features/indicators/`; documented in `ARCHITECTURE.md:401` and `:544` ("Production-Readiness Review"); `FRONTEND.md:1802-2015`. | —                    |

### 2.5 Feature Engineering Engine

| #   | Claim                                                        | Status            | Evidence                                                                                                                                                                                                                                                                                                                             | Missing (if partial)                                                                                            |
| --- | ------------------------------------------------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| 26  | Core pipeline (registry, generators, dataset assembly)       | VERIFIED          | `app/features/{registry,pipeline,base,dataset}.py`; `ARCHITECTURE.md:676` "Feature Engineering Engine".                                                                                                                                                                                                                              | —                                                                                                               |
| 27  | Production Hardening pass (identity, quality, search, scale) | VERIFIED          | `app/features/{quality,errors,validation}.py`; `ARCHITECTURE.md:807-972`.                                                                                                                                                                                                                                                            | —                                                                                                               |
| 28  | Versioning, lineage, correlation, cache, statistics pass     | VERIFIED          | `app/features/{lineage,correlation,statistics,cache,export}.py`, each a real module (not stubs); `ARCHITECTURE.md:973-1105`.                                                                                                                                                                                                         | —                                                                                                               |
| 29  | `ai_extensions.py` — declared future extension points        | PARTIAL by design | `app/features/ai_extensions.py` documents `NormalizationStats`/`FeatureNormalizer` (now **implemented** — see #38), and `SplitRatios`/`DatasetSplit` (used by #34). `LabelSpec`/`LabelGenerator` and `TrainValidationTestSplitter` were deleted this session as superseded by real code (`TargetPipeline`, `ChronologicalSplitter`). | Confirms this file is a live extension-point registry, not dead scaffolding — status is intentional, not a gap. |
| 30  | Frontend Feature Engineering page                            | VERIFIED          | `apps/dashboard/src/features/feature-engineering/`; route `src/app/(dashboard)/features/page.tsx`; `FRONTEND.md:2016-2276`.                                                                                                                                                                                                          | —                                                                                                               |

### 2.6 Dataset Validation & Quality Engine

| #   | Claim                            | Status   | Evidence                                                                                                                             | Missing (if partial) |
| --- | -------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| 31  | Rule engine + report             | VERIFIED | `app/dataset_validation/{engine,registry,report,base,errors}.py`; endpoints `app/api/v1/endpoints/dataset_validation.py` (2 routes). | —                    |
| 32  | Frontend Dataset Validation page | VERIFIED | `apps/dashboard/src/features/dataset-validation/`; route `src/app/(dashboard)/validation/page.tsx`; `FRONTEND.md:2277-2469`.         | —                    |

### 2.7 ML Dataset Builder

| #   | Claim                                            | Status   | Evidence                                                                                                                                                                                                           | Missing (if partial) |
| --- | ------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| 33  | Target generation + chronological split + export | VERIFIED | `app/ml_datasets/{split,export,pipeline,base,registry}.py`; `app/ml_datasets/split.py`'s own docstring: implements "the `split(dataset, ratios) -> DatasetSplit` contract `app.features.ai_extensions` documents." | —                    |
| 34  | Dataset History (persisted past builds)          | VERIFIED | `app/models/ml_dataset_build.py`; migration `20260827_608e8ba1ef82_add_ml_dataset_builds_table.py`; endpoints in `app/api/v1/endpoints/ml_datasets.py` (7 routes) include list/get/delete for builds.              | —                    |
| 35  | Frontend ML Dataset Builder page                 | VERIFIED | `apps/dashboard/src/features/ml-datasets/`; route `src/app/(dashboard)/ml-datasets/page.tsx`; `FRONTEND.md:2470-2607`.                                                                                             | —                    |

### 2.8 Experiment Management System

| #   | Claim                                                        | Status                        | Evidence                                                                                                                                                                                                                                                                                                                                                                                   | Missing (if partial) |
| --- | ------------------------------------------------------------ | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| 36  | CRUD + metrics + artifacts                                   | VERIFIED                      | `app/models/experiment.py`, `app/services/experiments.py`, endpoints `app/api/v1/endpoints/experiments.py` (9 routes); migration `20260826_fa0a2a1c8181_create_experiment_management_schema.py`.                                                                                                                                                                                           | —                    |
| 37  | `feature_set`/`target_config`/`split_config` editable in-app | VERIFIED (added this session) | `apps/dashboard/src/features/experiments/components/experiment-config-dialog.tsx` composes `FeatureSelector`/`TargetSelector`/`SplitConfigForm`; PATCHes `/experiments/{id}`; tests in `experiment-config-dialog.test.tsx` (7 tests) + `experiment-config.test.ts` (11 tests). Previously curl-PATCH-only, as `CLAUDE.md` and the original `ExperimentMetadataPanel` docstring documented. | —                    |

### 2.9 ML Training Framework + Baseline Model Framework

| #   | Claim                                                            | Status                                                    | Evidence                                                                                                                                                                                                                                                            | Missing (if partial)    |
| --- | ---------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| 38  | Per-column feature normalization (z-score/min-max)               | VERIFIED                                                  | `app/training/normalization.py` — `ColumnNormalizer`, `apply_normalization`; wired into `app/training/dataset_loader.py`; `TrainingJobCreateRequest.normalize_features` (default `true`); migration `20260830_d58d9f8bdab6_add_training_job_normalize_features.py`. | —                       |
| 39  | Logistic Regression adapter (real scikit-learn)                  | VERIFIED                                                  | `app/training/adapters/logistic_regression.py`; confusion matrix, ROC/PR curves, feature importance; `tests/training/test_logistic_regression.py`.                                                                                                                  | —                       |
| 40  | Linear Regression adapter (real scikit-learn)                    | VERIFIED                                                  | `app/training/adapters/linear_regression.py`; `tests/training/test_linear_regression.py`.                                                                                                                                                                           | —                       |
| 41  | Placeholder adapter (fabricated metrics, pipeline scaffolding)   | VERIFIED                                                  | `app/training/adapters/placeholder.py` — deliberately fake, per its own declared purpose.                                                                                                                                                                           | —                       |
| 42  | Pipeline/state machine/error reporting                           | VERIFIED                                                  | `app/training/{pipeline,state_machine,error_reporting,errors}.py`; endpoints `app/api/v1/endpoints/training.py` (10 routes).                                                                                                                                        | —                       |
| 43  | Training runs synchronously in-request (no worker)               | VERIFIED — and this is a real limitation, not a doc error | `TrainingJobService.run()`'s own docstring: "Runs synchronously within this call — no worker/queue service exists in this platform yet ... blocks for the duration of the ... pipeline run."                                                                        | See §4 Background Jobs. |
| 44  | Frontend ML Training page                                        | VERIFIED                                                  | `apps/dashboard/src/features/ml-training/`; route `src/app/(dashboard)/ml/training/page.tsx`.                                                                                                                                                                       | —                       |
| 45  | Create-Training-Job dialog warns when experiment config is empty | VERIFIED (added this session)                             | `create-training-job-dialog.tsx` — `experimentConfigIncomplete` check + `EmptyStateNotice` with a link to the experiment; tests in `ml-training-page.test.tsx`.                                                                                                     | —                       |

### 2.10 Model Evaluation & Benchmarking Engine

| #   | Claim                                                         | Status   | Evidence                                                                                                                                                                 | Missing (if partial) |
| --- | ------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| 46  | Evaluation engine + metric registry                           | VERIFIED | `app/evaluation/{engine,base,registry,errors}.py`, `app/evaluation/metrics/{classification,regression}.py`.                                                              | —                    |
| 47  | Benchmarking + persisted benchmark runs                       | VERIFIED | `app/evaluation/benchmark.py`; `app/models/evaluation_benchmark_run.py`; migration `20260829_34ade0f119b6_add_evaluation_benchmark_runs_table.py`.                       | —                    |
| 48  | 5 REST endpoints (metrics catalog, run, list/get/delete runs) | VERIFIED | `app/api/v1/endpoints/evaluation.py:92,107,127,175,191`; mounted via `app/api/v1/router.py:6,24`.                                                                        | —                    |
| 49  | Frontend Model Evaluation & Benchmarking page                 | VERIFIED | `apps/dashboard/src/features/ml-evaluation/` (261-line page + components/hooks calling the real API); route `src/app/(dashboard)/ml/evaluation/page.tsx`.                | —                    |
| 50  | Tests exist and pass                                          | VERIFIED | `tests/evaluation/test_benchmark.py`, `tests/api/test_evaluation_api.py` — both pass (`uv run pytest tests/evaluation tests/api/test_evaluation_api.py -q` → all green). | —                    |

**Note on claim framing**: this engine was described in the audit prompt as "claimed in-progress." Nothing in the actual planning docs (`ARCHITECTURE.md:1918-2210`, `FRONTEND.md:2847-3033`, `docs/api/API.md:1137-1285`) describes it as in-progress — all three describe it as a finished feature, including a follow-up "Production-Readiness Pass" (`ARCHITECTURE.md:2055`) layered on top. The only place it reads as not-yet-existing is `CLAUDE.md`, which predates it entirely (see §6).

### 2.11 Explicitly future / target-state (not built, and not claimed to be)

These appear in `docs/architecture/ContainerArchitecture.md`/`DomainModel.md`/`DataArchitecture.md` as intended full-system design, consistently marked target-state in every doc that mentions them, and confirmed absent in code:

| #   | Claim                                    | Status                         | Evidence                                                                                               |
| --- | ---------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 51  | Feature Store                            | MISSING (documented as future) | `ARCHITECTURE.md:2211` header only, no body content; no `app/` module.                                 |
| 52  | AI Research (beyond Training/Evaluation) | MISSING (documented as future) | `ARCHITECTURE.md:2218` header only.                                                                    |
| 53  | Prediction Service                       | MISSING (documented as future) | `ARCHITECTURE.md:2228` header only.                                                                    |
| 54  | Portfolio Management                     | MISSING (documented as future) | `ARCHITECTURE.md:2232` header only.                                                                    |
| 55  | Risk Engine                              | MISSING (documented as future) | `ARCHITECTURE.md:2236` header only.                                                                    |
| 56  | Order Management                         | MISSING (documented as future) | `ARCHITECTURE.md:2240` header only.                                                                    |
| 57  | Exchange Integration beyond Delta        | MISSING (documented as future) | `ARCHITECTURE.md:2244` header only; only Delta exists (§2.2).                                          |
| 58  | Monitoring (platform-wide)               | MISSING (documented as future) | `ARCHITECTURE.md:2248` header only; see §4 Logging & Monitoring for what minimal logging _does_ exist. |

---

## 3. Undocumented But Built

- **`fetchMarketResearch` is now actually consumed.** `CLAUDE.md` (and this repo's own prior-session notes) state it as "unused by any page." It is now wired into a real hook, `useMarketResearch` (`apps/dashboard/src/features/markets/hooks/use-markets-data.ts:87`), consumed by the Markets page's own detail panel — not by the still-placeholder `/research` route, but genuinely in use. `CLAUDE.md`'s claim is stale.
- **CoinGecko** is documented as a target external system (`SystemContext.md:68`) but wasn't named in the audit's connector list — included here for completeness; status is MISSING, identical to the other five (§2.3, #22).
- **`app/middleware/` and `app/utils/`** are real, tracked, empty packages (`__init__.py` only, no other files) — reserved extension points with literally nothing in them yet. Not mentioned as a gap anywhere; CORS is instead configured directly in `app/application.py:70-71` via Starlette's `CORSMiddleware`, not through the reserved `middleware/` package.
- **Backend test count has grown far beyond what any doc claims.** `README.md:101` and `CLAUDE.md` both cite "319 tests passing (93.74% coverage)" — the actual current count is **1406 tests, 97.30% coverage** (measured this session, `uv run pytest -q --cov=app`). Every subsystem in §2.5–2.10 was built after that 319-test snapshot.
- **Frontend test count is likewise far beyond documented numbers.** `README.md:102` cites "88 tests passing" for the dashboard (Health/Markets/History only, at the time). Actual current count: **1819 tests across 204 files**, covering every subsystem in §2.4–2.10 plus the placeholder pages' own (trivial) tests.
- **`docs/database/DATABASE.md`** is itself a real, current, evidence-grounded document (not a stub, contrary to what `CLAUDE.md` says) — it documents the Experiment Management and ML Training Framework schemas in detail. It is, however, itself slightly behind: it doesn't mention the `ml_dataset_builds` table (migration `608e8ba1ef82`) or the `training_jobs.normalize_features` column (migration `d58d9f8bdab6`), both added after this doc's own last major update.

---

## 4. Cross-Cutting Infrastructure

**Caching** — PARTIAL/MISSING depending on layer.

- Redis: provisioned in `infra/docker/docker-compose.yml:31-49` (real service, `redis:7-alpine`, healthcheck, `--requirepass`), declared as a dependency (`services/api/pyproject.toml:15`, `redis>=5.2.0`, resolved to `redis==8.1.0` in `uv.lock:1065`) — but **zero usage**. `grep -rn "redis" app --include="*.py" -i` matches only comments (`app/indicators/cache.py`, `app/features/cache.py`, `app/state/__init__.py`) explicitly stating it is "deliberately _not_ Redis-backed." No `import redis`, no `REDIS_URL` read in `app/core/config.py`.
- In-process caching **does** genuinely exist and is wired in: `IndicatorCache` (`app/indicators/cache.py:76`, used at `app/dependencies/indicators.py:31` and `app/features/builtin/__init__.py:67`) and `FeatureCache` (`app/features/cache.py:63`, used at `app/dependencies/features.py:41`). Both are per-process dicts — invisible across multiple API instances, never shared/distributed.

**Background jobs / task queue** — MISSING (no real queue exists).

- No Celery/RQ/arq/APScheduler/dramatiq dependency anywhere in `pyproject.toml`.
- The only periodic execution is `CandleSyncScheduler` (`app/services/candle_sync.py:56`), an `asyncio.Event().wait(timeout=self._interval_seconds)` loop running inside the same API process — not a separate worker, no persistence of job state, dies if the API process dies.
- `POST /training-jobs/{id}/run` is fully synchronous and blocking (confirmed via `TrainingJobService.run()`'s own docstring, `app/services/training.py`) — a slow real model training run holds the HTTP request open for its entire duration.

**Rate limiting** — PARTIAL.

- Outbound (respecting Delta's limits): real. `RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})` (`app/integrations/delta/client.py:35`), explicit `RateLimitError` handling (`client.py:313-314,429`), tested (`tests/unit/delta/test_client.py:168` `test_rate_limit_retries_then_succeeds`, `:194` `test_rate_limit_exhausted_raises_rate_limit_error`). This is retry-with-backoff, not a proactive token-bucket throttle.
- Inbound (protecting this platform's own API): **none**. No slowapi/starlette-limiter or hand-rolled middleware anywhere. Confirmed both by code search and by `docs/api/API.md:1333-1336`'s own "Rate Limiting: Not implemented" section — the one place this is honestly and currently documented.

**Secrets / config management** — plain env vars, no manager.

- `app/core/config.py:12,15,19-20` — `pydantic_settings.BaseSettings` reading `.env` via `SettingsConfigDict(env_file=".env", ...)`. No `SecretStr` wrapping on credential fields, no Vault/AWS Secrets Manager/keyring integration (`grep` for all three in `pyproject.toml` → no matches). This matches the project's documented stage; not flagged elsewhere as a gap, so noted here only because the audit explicitly asked.

**Logging and monitoring** — PARTIAL (logging real but minimal; monitoring absent).

- `app/core/logging.py` — real, but literally `logging.basicConfig(level=..., format="%(asctime)s %(levelname)s [%(name)s] %(message)s")`. No structured (JSON) logging, no log aggregation config.
- No tracing (no OpenTelemetry dependency), no metrics export (no Prometheus/statsd dependency), no error tracking (no Sentry dependency). `grep -n "sentry|opentelemetry|prometheus" pyproject.toml -i` → no matches.
- Matches the still-open "M10 Monitoring & Observability" milestone status — not a doc/code conflict, just confirmed genuinely not built.

**Authentication / Authorization** — MISSING, and honestly documented as such.

- No auth dependency, no JWT/OAuth/session code for this platform's own API (every `jwt`/`auth`/`login` grep hit is either Delta's own outbound key-auth, or system/schema files unrelated to inbound auth).
- `docs/api/API.md:1321-1324` states this plainly: "None — the current surface is read-only and public." No conflict here, just confirmed current.

**CI/CD** — MISSING entirely.

- `find . -maxdepth 2 -iname ".github"` → no results anywhere in the repo. Every quality gate (`ruff`, `eslint`, `tsc`, `pytest`, `vitest`, `prettier`, `markdownlint`) runs only via local Husky git hooks (`.husky/pre-commit`, `.husky/pre-push`) — confirmed present and wired (`pre-commit` → lint-staged + gitleaks; `pre-push` → `prettier --check .` + `markdownlint`). Nothing runs automatically on push/PR at the platform level (there is no remote CI to run it).

---

## 5. Test Coverage

**Backend** (`uv run pytest -q --cov=app`, executed this session):

| Metric            | Value                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tests collected   | 1406                                                                                                                                                |
| Failures / Errors | 0 / 0                                                                                                                                               |
| Skipped           | 18 (4 performance opt-in, 6 Delta-integration opt-in [real network], 8 Postgres-specific opt-in [local Postgres auth mismatch in this environment]) |
| Line coverage     | 97.30% (gate: 80%, `pyproject.toml`)                                                                                                                |

Per-directory test counts (from the JUnit report, by top-level `tests/` folder):

| Folder                  | Tests | Folder                  | Tests |
| ----------------------- | ----- | ----------------------- | ----- |
| `unit/`                 | 297   | `api/`                  | 251   |
| `training/`             | 182   | `features/`             | 215   |
| `ml_datasets/`          | 110   | `services/`             | 88    |
| `dataset_validation/`   | 70    | `evaluation/`           | 53    |
| `experiments/`          | 44    | `websocket/`            | 38    |
| `event_bus/`            | 13    | `repository/`           | 13    |
| `state_manager/`        | 12    | `processing/`           | 10    |
| `integration/` (opt-in) | 6     | `performance/` (opt-in) | 4     |

Gaps: real-network Delta integration tests (`tests/integration/delta/`) and a real-Postgres repository suite (`tests/repository/test_candles_postgres.py`, `test_training_postgres.py`) exist but did not run in this environment — the former needs `--run-integration` against the live exchange, the latter needs a reachable `eth_platform_test` Postgres database (this environment's local Postgres rejected the configured test credentials: `password authentication failed for user "research"`). Both are real, checked-in tests, just not exercised here — see §7.

**Frontend** (`npx vitest run`, executed this session):

| Metric               | Value                                                                         |
| -------------------- | ----------------------------------------------------------------------------- |
| Test files           | 204, all passing                                                              |
| Tests                | 1819, all passing                                                             |
| `tsc --noEmit`       | Clean, 0 errors                                                               |
| `eslint` (repo-wide) | 1 pre-existing warning (`no-console` in `src/lib/api/client.ts:32`), 0 errors |

Coverage is exercised per-feature (component behavior, hook logic, Zod schema validation) rather than measured as a single repo-wide percentage — no `vitest --coverage` gate is configured in this project (confirmed: no `coverage` threshold in `vitest.config.ts`/`package.json` scripts).

Not independently verified this session: whether every one of the 204 test files exercises real user-facing behavior versus a shallow smoke test — that would require reading all 204 files individually, out of this audit's budget. The counts above are what actually ran and passed, not a judgment on depth.

---

## 6. Document Conflicts

- **`CLAUDE.md` (dated 2026-08-22, per its own header) is severely stale relative to the current codebase.** Its "Current Completed Features" section describes only Market Data + a dashboard Health/Markets/History/Live-Market shell. It does not mention Feature Engineering, Dataset Validation, ML Dataset Builder, Experiment Management, ML Training Framework, Baseline Model Framework, or Model Evaluation & Benchmarking at all — all seven of which are fully built, tested, and documented as current in `ARCHITECTURE.md` and `FRONTEND.md` (both dated 2026-08-30). `README.md`'s "Development Status" section (also stale, same era) repeats the same outdated picture and cites "319 tests"/"88 tests" — the real current counts are 1406/1819 (§5).
- **`TASKBOOK.md`'s "Milestone Summary" table (`TASKBOOK.md:117-136`) shows every milestone M0–M11 at "0% / Planned"**, including M2 (Feature Engineering) and M3 (AI Research & Training) — both of which are fully implemented per §2.5–2.10. `README.md:113-115` itself already flags this: "its progress tables currently lag behind actual implementation and are being brought up to date."
- **Milestone numbering does not have a clean mapping for what's actually built**, and this audit could not manually invent one without guessing: the user's own audit request labeled Model Evaluation & Benchmarking as "Milestone 8," but `TASKBOOK.md`'s table defines **M8 = Risk Management** (not built) — Model Evaluation, along with Feature Engineering/Dataset Validation/ML Dataset Builder/Experiments/Training, doesn't correspond to any single M0–M11 label cleanly. `CLAUDE.md` itself previously declined to relabel `TASKBOOK.md`'s task IDs for exactly this reason ("the existing task IDs don't map cleanly onto what was actually built"). This mismatch is unresolved and should not be papered over by either doc unilaterally.
- **`ROADMAP.md` is a 15-line empty stub** ("Status: Draft," no milestones, no timeline) — it makes no claims to conflict with, but its existence alongside a much more detailed (if also stale-in-places) `TASKBOOK.md` milestone table is itself a duplication `CLAUDE.md` never flagged.
- **Root `ARCHITECTURE.md` vs `docs/architecture/ARCHITECTURE.md`** — the root file (2282 lines) is a real, current, detailed document; `docs/architecture/ARCHITECTURE.md` (11 lines) is a genuinely empty stub with the same title. `CLAUDE.md` already flagged this exact duplication as unresolved; still unresolved.
- **Root `DECISIONS.md` vs `docs/decisions/DECISIONS.md`** — same pattern: root file has a fully-designed ADR methodology (203 lines) but an entirely empty decision index (`DECISIONS.md:178-203`, every row "—"); `docs/decisions/DECISIONS.md` is an 11-line bare stub. Zero ADRs exist despite clearly ADR-worthy decisions already made in code (PostgreSQL, FastAPI, scikit-learn as the baseline-model framework, event-bus-over-broker, in-process caching over Redis, etc.). `CLAUDE.md` already flagged this; still unresolved.
- **`docs/database/DATABASE.md` is current but incomplete** relative to the actual migration history — see §3, last bullet.

---

## 7. Open Questions

- **Real-Postgres repository tests** (`tests/repository/test_candles_postgres.py`, `test_training_postgres.py`) and **real-network Delta integration tests** (`tests/integration/delta/*`) exist as checked-in code but did not execute in this environment — the former because the locally-running Postgres instance rejected the test suite's configured credentials (`password authentication failed for user "research"` against `postgresql+asyncpg://research:research@localhost:5432/eth_platform_test`), the latter because they require `--run-integration` against the live Delta Exchange API, which this audit did not invoke to avoid hitting a real third-party production API in the course of a documentation exercise. Their **presence and content look real** (not stubs) but their current pass/fail status is unverified.
- **Depth of the 204 frontend test files** was not individually audited — the counts in §5 confirm they run and pass, not that each one exercises meaningfully deep behavior versus a shallow render check. A sampling pass would be needed to make a depth claim.
- **Whether any of the six external-data-connector env vars (`MARKETAUX_API_KEY`, `ETHERSCAN_API_KEY`, `FRED_API_KEY`, `DEFILLAMA_BASE_URL`, `COINGECKO_API_KEY`) are read by anything outside `services/api`** (e.g. a script under `scripts/`, or tooling outside the two workspaces this audit focused on) was checked only within `services/api` and `apps/dashboard`; `scripts/`, `tools/`, and `packages/` are confirmed-empty placeholder directories per their own README files, so this is treated as settled, not truly open — noted for completeness since it wasn't re-verified line-by-line in this pass.
- **Whether `app/middleware/`/`app/utils/` being empty is intentional scaffolding or an abandoned earlier plan** could not be determined from the code alone — no comment or doc explains their existence as empty packages (unlike, e.g., `ai_extensions.py`'s explicit "why these six and not others" framing for its own placeholders).
