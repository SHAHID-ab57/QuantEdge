# CLAUDE.md

This file is the primary context document for Claude Code (and any future AI
assistant) working in this repository. It was produced by a full discovery pass
over the codebase, existing documentation, and tooling on 2026-08-22. Every claim
below was verified by reading the actual source, config, or docs — nothing here
is aspirational unless explicitly marked as such.

This repository previously used **OpenCode** as its AI development assistant.
From this point forward, **Claude Code is the primary AI development environment**
for this project. The only OpenCode-specific references found in the repo were
two lines in `TASKBOOK.md` describing the "one OpenCode prompt → one commit"
workflow; these have been updated to say "Claude Code prompt" instead. No other
OpenCode artifacts, configs, or scripts exist anywhere in the repository.

---

## Project Overview

**Eth AI Platform** (`package.json` name: `eth-ai-platform`) — a professional
AI-powered Ethereum Market Analysis and Probabilistic Prediction Platform for
research, education, and decision support. It ingests, processes, and analyzes
Ethereum derivatives market data (via Delta Exchange India) to produce
probabilistic forecasts and quantitative research outputs. The platform
explicitly does **not** provide financial advice or guarantee profitable
trading; outputs are framed as analytical decision support only.

Source: `README.md`, `PROJECT.md`.

## Purpose

Per `PROJECT.md` (the most detailed vision document in the repo — see
[Documentation Landscape](#documentation-landscape)): combine quantitative
finance, machine learning, data engineering, and production software
engineering into one modular system. Stated goals span building a reliable
market data ingestion platform, a probabilistic prediction engine, and
continuous AI model improvement/retraining. Target users (11 personas defined
in `PROJECT.md`) include quantitative/AI/ML researchers, data scientists,
portfolio analysts, traders of varying skill levels, students, educators, and
software engineers. Repository philosophy (`README.md`): architecture-first,
bounded-context ownership, reproducible research, probabilistic thinking
(uncertainty communicated honestly), professional engineering standards.

## Current Architecture

The platform is implemented today as **two deployable units**:

- **`services/api`** — a FastAPI backend that ingests and serves Ethereum
  perpetual/spot market data from Delta Exchange, with an in-process event bus,
  an in-memory market state manager, and a candle/market persistence layer on
  PostgreSQL.
- **`apps/dashboard`** — a Next.js 15 / React 19 / MUI 7 frontend that
  REST-polls the API to render health, markets, and history views.

There is currently **no server-to-browser push channel** — the dashboard polls
REST endpoints on an interval; it does not open a WebSocket to the backend
(see [WebSocket Flow](#websocket-flow) for the important nuance about what
"WebSocket" means in this codebase). No worker/queue service, feature store,
prediction engine, backtesting engine, or trading execution service exists yet
— those are documented only as future bounded contexts in
`docs/architecture/DomainModel.md` and `ContainerArchitecture.md`.

Six of the eight files in `docs/architecture/` are fully written, detailed
design documents (C4-style) describing the **intended full system** — read
those before making structural decisions:

| Document                                     | Content                                                                                                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/architecture/ContainerArchitecture.md` | C4 Level-2: 21 containers (web, API, collector, feature store, prediction service, risk engine, etc.), a Mermaid diagram, 10 architecture decisions     |
| `docs/architecture/DataArchitecture.md`      | 18 data domains (D1–D18), full data lifecycle (raw → validated → normalized → stored → features → dataset → model → prediction → execution → analytics) |
| `docs/architecture/DomainModel.md`           | 13 DDD bounded contexts, communication matrix, repository mapping                                                                                       |
| `docs/architecture/EngineeringStandards.md`  | The actual coding-conventions doc — see [Coding Standards](#coding-standards)                                                                           |
| `docs/architecture/RepositoryStructure.md`   | The intended full monorepo tree (13 bounded-context services, etc.)                                                                                     |
| `docs/architecture/SolutionArchitecture.md`  | C4 Level-3: 10 solution-level workflows                                                                                                                 |
| `docs/architecture/SystemContext.md`         | C4 Level-1: external systems (Delta Exchange India, CoinGecko, Marketaux, Etherscan, FRED, Alternative.me, DefiLlama)                                   |
| `docs/architecture/ARCHITECTURE.md`          | Empty (bare headers only) — **not** the same template as root `ARCHITECTURE.md`                                                                         |

Only the **Market Data** bounded context and a health/observability slice of
the dashboard are implemented so far; everything else in those documents is
target-state, not current-state.

## Technology Stack

**Backend (`services/api`)**

- Python **3.13+** (`.python-version`, `pyproject.toml`), package manager **uv** (`uv.lock` committed)
- FastAPI (`>=0.115`), Uvicorn (standard extras), Pydantic v2 + pydantic-settings
- SQLAlchemy 2.x (async), asyncpg driver, Alembic migrations
- httpx (outbound REST to Delta Exchange), `redis` is a declared dependency but **not yet wired into any code path**
- Lint/format: **ruff** (`target-version py313`, line-length 100, rule sets `E,F,I,N,UP,B,SIM`); type checking via `pyrightconfig.json` (basic mode)
- Testing: pytest + pytest-asyncio (`asyncio_mode="auto"`), pytest-cov (80% gate, currently ~94%), aiosqlite for DB-less test runs, asgi-lifespan

**Frontend (`apps/dashboard`)**

- Next.js `^15.3` (App Router, `typedRoutes: true`), React `^19`, TypeScript `^5.6` (strict)
- MUI v7 (`@mui/material`, `@mui/icons-material`, `@mui/material-nextjs`) + Emotion, dark-only theme
- TanStack Query v5 (server state), Zustand v5 (local UI state only — sidebar open/collapsed)
- react-hook-form + Zod v4 (forms **and** runtime validation of every API response)
- Axios (HTTP client), Vitest v3 + Testing Library (jsdom)

### Repo-wide tooling

- pnpm `>=9` workspaces (`pnpm-workspace.yaml`: `apps/*`, `services/*`, `packages/*`, `tools/*`) orchestrated by **Turborepo** (`turbo.json`)
- Node `>=20`, root TypeScript base config (`tsconfig.base.json`) with strict flags
- Root ESLint flat config (`eslint.config.mjs`) as a framework-agnostic baseline that `apps/dashboard` extends
- Prettier (100-char width, single quotes, 2-space) + markdownlint for docs
- Husky git hooks + commitlint (Conventional Commits) + lint-staged + gitleaks — see [Development Workflow](#development-workflow)
- Docker Compose for local infra (Postgres + Redis only — see [Environment Variables](#environment-variables))
- **No CI/CD is configured** — no `.github/`, no other CI config of any kind exists in the repo. All quality gates run only via local git hooks.

## Repository Structure

```text
apps/dashboard/        Next.js frontend (the only app implemented so far)
services/api/          FastAPI backend (the only service implemented so far)
packages/               Empty — reserved for shared libraries (README only)
infra/docker/           docker-compose.yml (Postgres + Redis), README, .env.example
configs/                Repo-level tooling config docs (environment.example.md, README)
docs/                   Platform documentation (see Documentation Landscape below)
scripts/                Empty — reserved for automation scripts (README only)
tests/                  Empty — reserved for cross-cutting/E2E tests (README only)
tools/                  Empty — reserved for dev tooling/scaffolding (README only)
```

`docs/architecture/RepositoryStructure.md` documents a much larger _intended_
structure (13 bounded-context services under `services/`, multiple apps,
shared packages). Only `services/api` and `apps/dashboard` exist today; treat
the rest of that document as a target, not current state.

## Backend Architecture

Entry point chain: `app/main.py` → `create_app()` in `app/application.py`
(FastAPI app factory, CORS middleware, exception handlers, lifespan) →
`app/runtime.py`'s `Runtime` (composition root).

**`Runtime`** always owns an `EventBus` and a `MarketStateManager` (cheap,
in-memory). If `MARKET_DATA_LIVE=true` it additionally builds a
`MarketDataPipeline` + `DeltaWebSocketClient`, subscribes to configured
symbols, and starts the client. Independently, if candle-sync is enabled, a
`CandleSyncScheduler` runs periodic catch-up ingestion. Startup fails fast
(`RuntimeError`) if a configured database is unreachable; the app can also run
fully DB-less (health/dev scenarios).

**Domain model** (SQLAlchemy async ORM, `app/models/`):

- `Exchange` — name/slug, country, timezone, is_active
- `Market` — FK→Exchange, unique `(exchange_id, symbol)`, base/quote asset, `market_type` (spot/perpetual/expiry), plus Delta-specific metadata (`delta_product_id`, `delta_contract_type`, `tick_size`, `funding_method`, `funding_interval_seconds`, `listing_date`)
- `Candle` — FK→Market, unique `(market_id, timeframe, open_time)`, OHLCV as `NUMERIC(38,18)`, check constraints for OHLC dominance/non-negativity/time-ordering

**Services & repositories** (`app/services/`, `app/repositories/`): routers
never touch SQL directly — `MarketDataService` is the sole entry point
consumed by API routes; `CandleRepository`/`MarketRepository` hold all query
logic. Other services: `candle_ingest` (idempotent historical fetch → validate
→ persist, windowed ≤2000 candles), `candle_sync` (scheduler wrapper around
ingest), `candle_validation` (read-only data-quality reporting: gaps,
duplicates, OHLC/UTC/alignment checks, quality score), `market_sync`
(idempotent Delta product-catalog → `exchanges`/`markets` upsert).

**Migrations** (`services/api/alembic/versions/`), verified applied to head
against the local Postgres instance during this discovery pass:

1. `592cf2283d14` — create market data schema (`exchanges`, `markets`, `candles`)
2. `1402faec05f9` — make `candles.quote_volume` nullable (Delta candles carry no quote volume)
3. `0d1c3a9b5e2f` — add Delta-specific market metadata columns

## Frontend Architecture

Root layout wires MUI's `AppRouterCacheProvider` + `AppProviders`
(Theme + TanStack Query). `src/app/page.tsx` redirects to `/dashboard`. All
real pages live under the `(dashboard)` route group, wrapped in `AppShell`
(sidebar + top bar), with group-level `error.tsx`/`loading.tsx`.

**Routes and implementation status:**

| Route          | Status                                                                                                                                                                              |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/health`      | Implemented — platform/DB/bus/state/processing health cards, polls `/api/v1/system/*` every 10s                                                                                     |
| `/markets`     | Implemented — filterable/sortable table + detail panel, quality scoring                                                                                                             |
| `/history`     | Implemented — historical candle browser, CSV/JSON export, stats/quality/performance cards                                                                                           |
| `/dashboard`   | Placeholder (`PlaceholderPage` component, no logic)                                                                                                                                 |
| `/research`    | Placeholder — note: a `fetchMarketResearch` API function and `MarketResearchSchema` already exist in `src/lib/api/market.ts` / `src/types/api/market.ts` and are unused by any page |
| `/live-market` | Placeholder                                                                                                                                                                         |
| `/settings`    | Placeholder                                                                                                                                                                         |

**Feature module pattern** (`src/features/<name>/`): `<name>-page.tsx` +
`components/` + `hooks/` + `lib/` + a co-located `<name>-page.test.tsx`. Follow
this pattern for any new feature area.

**API client** (`src/lib/api/client.ts`): single Axios instance, base URL from
`NEXT_PUBLIC_API_URL`, bearer token injected from `sessionStorage`
(`src/lib/api/session.ts`), typed error normalization
(`src/lib/api/errors.ts`), 401 → redirect to `/`. Every response is
`schema.parse()`d against a Zod schema before use — never trust an API
response as typed without also runtime-validating it, matching this
codebase's existing convention.

## Database

PostgreSQL 17 (via Docker Compose in dev), accessed through SQLAlchemy 2.x
async + asyncpg. Schema: `exchanges` → `markets` → `candles` (see
[Backend Architecture](#backend-architecture)). Migrations are managed by
Alembic (`services/api/Makefile` targets: `db-create-migration`, `db-upgrade`,
`db-downgrade`, `db-history`, `db-current`, `db-stamp`). `docs/database/DATABASE.md`
is currently an empty stub — `docs/domain/MarketDataDomain.md` is the real,
detailed source for the data model (entities, constraints, business rules).

## Event Flow

`app/events/bus.py`'s `EventBus` is a broker-free, in-process pub/sub keyed by
`event_type` string. `subscribe()` registers async handlers in a
`dict[str, set[Handler]]`; `publish()` schedules one `asyncio.Task` per
matching handler (fire-and-forget — never blocks the publisher, handler
failures are isolated and logged, never propagate).

Flow for live market data: Delta WS message → `DeltaMessageParser` →
`DeltaNormalizer` (exchange-specific → domain models in
`app/marketdata/models.py`) → wrapped in bus events
(`TradeEventReceived`/`TickerUpdated`/`OrderBookUpdated`, defined in
`app/marketdata/bus_events.py`) → `bus.publish()` → consumed by
`MarketStateManager` (and any future subscriber). `MarketStateManager` does a
synchronous last-writer-wins update per symbol; it never awaits mid
read-modify-write, so it is safe under single-event-loop concurrency.

Reference-only handlers (`LoggingHandler`/`DebugHandler` in
`app/events/handlers.py`) exist but are **not wired into the runtime by
default** — they exist for documentation/testing purposes.

## WebSocket Flow

**Important nuance verified during this pass:** `app/ws/` is **not** a
server-side WebSocket endpoint for browser/dashboard clients — there is no
`@router.websocket(...)` route anywhere in `app/api/`. It is a
protocol-agnostic **outbound** WebSocket client toolkit (connection
management with reconnect/heartbeat, message dispatch, parsing, subscription
tracking), consumed exclusively by
`app/integrations/delta/websocket/client.py` to talk **outward** to Delta
Exchange's WebSocket API (auth via HMAC key-auth, channel
subscribe/resubscribe on reconnect).

The dashboard has **no browser-side WebSocket client at all** — despite UI
elements that look "live" (e.g. `live-status.tsx`'s connected chip, the health
page's "WebSocket connected" indicator), these are derived purely from
REST-polled fields (`delta_ws`, `last_ws_message_at`) on
`/api/v1/system/status`, refreshed every 10s. `NEXT_PUBLIC_WS_URL` is defined
and Zod-validated in `src/config/env.ts` but referenced nowhere else in the
frontend — it is reserved for future use, not currently consumed. If a future
milestone adds real-time push to the browser, it will need a **new** FastAPI
WebSocket route — none exists to reuse today.

## API Structure

Every route below is mounted twice — under `/api/v1/*` and unversioned at
`/*` (`app/api/router.py`). No authentication exists on any route yet.

| Method | Path                              | Purpose                                                                              |
| ------ | --------------------------------- | ------------------------------------------------------------------------------------ |
| GET    | `/health`                         | Liveness + DB connectivity (503 if DB unreachable)                                   |
| GET    | `/markets`                        | List all markets                                                                     |
| GET    | `/markets/{symbol}/timeframes`    | Distinct timeframes with stored candles                                              |
| GET    | `/markets/{symbol}/research`      | Per-timeframe coverage/completeness metrics                                          |
| GET    | `/markets/{symbol}/candles`       | Paginated candles + statistics + quality + meta                                      |
| GET    | `/markets/{symbol}/latest`        | Newest candle for a market/timeframe                                                 |
| GET    | `/markets/{symbol}/candles/stats` | Aggregate stats over a range                                                         |
| GET    | `/system/health`                  | Per-component status (api, database, delta_rest, delta_ws, event_bus, state_manager) |
| GET    | `/system/status`                  | Uptime, environment, live connection state, freshness timeline                       |
| GET    | `/system/metrics`                 | Ingestion/pipeline/state/bus counters                                                |

Domain errors (`market_not_found`, `candle_not_found`, `invalid_timeframe`,
`invalid_range`, `limit_exceeded`, `invalid_sort`) surface as structured
`{code, detail}` JSON via `AppError` subclasses. `docs/api/API.md` documents
this surface accurately and is current.

## Coding Standards

The authoritative source is `docs/architecture/EngineeringStandards.md` (456
lines, fully written — read it in full before large changes). Verified,
concrete conventions actually enforced or observed in code:

- **Formatting**: Prettier for JS/TS/MD/JSON/YAML (100-char width, single
  quotes, semicolons, trailing commas, LF endings); ruff format for Python.
  ⚠️ `ruff format --check .` in `services/api` currently reports **78 files
  would be reformatted** — the working tree has drifted from the configured
  formatter. `pnpm format:check` at the repo root also currently fails (81
  files). See [Known Limitations](#known-limitations).
- **Linting**: root ESLint flat config + `next/core-web-vitals` in the
  dashboard; ruff (`E,F,I,N,UP,B,SIM`) in the API. Both currently pass with
  zero errors (two pre-existing warnings only).
- **TypeScript**: `strict: true`, `noUncheckedIndexedAccess`,
  `noUnusedLocals/Parameters`, `verbatimModuleSyntax` — do not weaken these.
- **Commit messages**: Conventional Commits, enforced by commitlint
  (`type(scope): description`, lower-case, no trailing period, max 100 chars/line).
- **Every API response is runtime-validated with Zod on the frontend** —
  follow this pattern for any new API client function.
- **Routers never touch SQL** — always go through a service → repository.
- **Domain errors are typed exceptions**, not ad-hoc HTTP responses.

## Naming Conventions

Per `docs/architecture/EngineeringStandards.md` and observed code: kebab-case
directories/files (`live-status.tsx`, `use-market-url-state.ts`), PascalCase
for classes/components, camelCase for functions/variables in TS,
snake_case for Python modules/functions, feature-scoped folders
(`src/features/<name>/{components,hooks,lib}`).

## State Management

- **Frontend server state**: TanStack Query (`src/lib/query/queryClient.ts`:
  `staleTime` 30s, `gcTime` 5min, `retry: 1`, `refetchOnWindowFocus: false`).
- **Frontend local UI state**: Zustand (`src/store/ui-store.ts`) — currently
  only sidebar open/collapsed flags; not used for server data.
- **Backend runtime state**: `MarketStateManager` (in-memory, per-symbol
  latest trade/ticker/order-book/candle) — no Redis-backed or persisted state
  cache exists yet, despite `redis` being a declared backend dependency.

## Testing Strategy

**Backend** (`services/api/tests/`, pytest + pytest-asyncio,
`asyncio_mode="auto"`): directories map 1:1 to architecture layers (`unit/`,
`api/`, `repository/`, `services/`, `websocket/`, `event_bus/`, `processing/`,
`state_manager/`, `integration/delta/`, `performance/`). Default test run uses
**no real network and no real database** — `tests/conftest.py` forces empty
`DATABASE_URL`/`DB_URL` and DB-backed tests run against an in-memory SQLite
engine. `tests/integration/delta/*` hits the **real live** Delta Exchange
REST/WS API and is opt-in only (`--run-integration` flag / `integration`
marker). `tests/performance/*` is similarly opt-in (`--run-performance`).
`tests/repository/test_candles_postgres.py` targets a real Postgres test DB
(`postgres` marker) and auto-skips if unreachable. Coverage gate is 80%
(`pyproject.toml`); actual coverage at time of this pass was **93.74%**, all
319 non-skipped tests passing.

**Frontend** (`apps/dashboard`, Vitest + Testing Library, jsdom): 6 test files
covering the three implemented features (`health`, `history`, `markets` —
component behavior, loading/error/empty states, URL-state sync, filtering,
sorting, export) plus Zod schema validation tests for API types. 88/88 tests
passing. Placeholder pages have no tests (no logic to test).

**No end-to-end/cross-cutting tests exist** — `tests/` at the repo root is an
empty placeholder (README only).

## Environment Variables

Three separate `.env.example` files exist and have **diverged** — treat the
service-level files as the source of truth, not the root template:

- **Root `.env.example`** — an aspirational/umbrella template: `APP_ENV`,
  `APP_PORT`, `APP_LOG_LEVEL`, `DATABASE_URL`, `REDIS_URL`, JWT vars, Delta
  Exchange vars prefixed `EXCHANGE_*`, market-data-provider keys
  (CoinGecko/Marketaux/Etherscan/FRED), object storage, SMTP. Many of these
  are not yet consumed by any actual service.
- **`services/api/.env.example`** — the real, narrower set actually read by
  `app/core/config.py`: `APP_ENV`, `APP_LOG_LEVEL`, `DATABASE_URL` (asyncpg),
  `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_ECHO`, and Delta Exchange vars
  prefixed **`DELTA_*`** (not `EXCHANGE_*` — a naming mismatch with the root
  template worth resolving in a future cleanup).
- **`apps/dashboard/.env.example`** — `NEXT_PUBLIC_API_URL`,
  `NEXT_PUBLIC_WS_URL` (unused, reserved), `NEXT_PUBLIC_APP_NAME`. Validated
  at startup by a Zod schema in `src/config/env.ts`.
- **`infra/docker/.env.example`** — `POSTGRES_USER/PASSWORD/DB`, `POSTGRES_PORT`
  (default `5433`, note this differs from Postgres's own default 5432 inside
  the container), `REDIS_PASSWORD`, `REDIS_PORT`.

## Development Workflow

```bash
pnpm install                       # installs deps, wires Husky hooks via `prepare`
cp .env.example .env                # repeat per-service as needed (see above)
docker compose -f infra/docker/docker-compose.yml up -d   # Postgres + Redis
cd services/api && uv sync
uv run alembic upgrade head
uv run fastapi dev app/main.py     # or: uvicorn app.main:app --reload
cd apps/dashboard && pnpm dev       # from repo root: pnpm --filter dashboard dev
```

**Git hooks (Husky, `.husky/`)** — all currently active and verified:

- `pre-commit`: `lint-staged` (per-file eslint --fix / prettier / markdownlint
  --fix depending on file type), then `gitleaks protect --staged` if gitleaks
  is installed (soft-skips otherwise).
- `commit-msg`: `commitlint --edit` — Conventional Commits enforced.
- `pre-push`: `prettier --check .` **and**
  `markdownlint docs README.md PROJECT.md REQUIREMENTS.md`. ⚠️ Verified during
  this pass that `prettier --check .` **currently fails** (81 files need
  reformatting) — pushing from a clean clone will be blocked by this hook
  until the working tree is reformatted. `markdownlint` currently passes.

**Branch/commit convention**: Conventional Commits
(`type(scope): description`), branch naming `{type}/{task-id}-{description}`
per `docs/architecture/EngineeringStandards.md`.

## Current Completed Features

- FastAPI backend scaffolded with async SQLAlchemy + PostgreSQL, structured
  config/logging/exception handling
- Alembic migration system with 3 applied migrations (schema, nullable fix,
  Delta metadata columns) — verified at head against a live Postgres instance
- Delta Exchange REST client (signed requests, retries, typed errors) and
  outbound WebSocket client (reconnect/heartbeat/auth/resubscribe)
- Market/candle data model, repositories, and services (ingest, sync,
  validation with a quality score)
- In-process async event bus and in-memory market state manager
- Market data processing pipeline (parse → normalize → validate → publish)
- Read-only market data + system health/status/metrics REST API (mounted at
  both `/api/v1/*` and unversioned `/*`)
- Next.js dashboard shell (sidebar/top-bar/theme/providers) with three fully
  implemented feature pages: **Health**, **Markets**, **History** (with
  CSV/JSON export)
- Backend test suite (319 tests, 93.74% coverage) and frontend test suite (88
  tests) — both passing as of this discovery pass

## Current Research Features

None yet. `PROJECT.md`'s vision (prediction engine, feature store, AI model
training/retraining, backtesting) is entirely aspirational — no code for any
research/ML capability exists in the repository today. The `/research`
dashboard page and its backing `fetchMarketResearch` API function exist but
are unconnected (page renders a placeholder, not the research API).

## Known Limitations

- No authentication/authorization on any API route.
- No server→browser push channel; "live" UI indicators are REST-polled, not
  real-time.
- `redis` is a declared backend dependency with no wired usage anywhere.
- No CI/CD pipeline — all quality gates are local-only (git hooks).
- Formatting has drifted: both `pnpm format:check` (root, 81 files) and
  `ruff format --check .` (services/api, 78 files) currently fail. The
  `pre-push` hook will block pushes until this is remediated.
- Root-level status documents (`README.md`'s prior "Development Status",
  `TASKBOOK.md`'s progress tables, `DECISIONS.md`'s empty decision index) had
  drifted significantly out of sync with actual implementation progress — see
  [Documentation Landscape](#documentation-landscape).
- `services/api/.env`, `.coverage`, `coverage.xml`, `htmlcov/` are present
  locally but correctly gitignored (verified not tracked).
- Local dev environment note (not a repo defect): the Redis container in
  `infra/docker/docker-compose.yml` failed to start during this pass because
  port 6379 was already bound by a non-Docker Redis process on the host
  machine; Postgres started/ran without issue.

## Future Milestones

Per `TASKBOOK.md`'s milestone list (status fields in that file are stale —
see above): M1 Data Layer, M2 Feature Engineering, M3 AI Research & Training,
M4 Prediction Engine, M5 Backtesting, M6 Paper Trading, M7 Portfolio
Analytics, M8 Risk Management, M9 Production Readiness, M10 Monitoring &
Observability, M11 Community & Expansion. Treat these as directional, not a
committed schedule — no dates or detailed task breakdowns exist beyond the
top-level names.

## Important Commands

```bash
# Repo root (all workspaces, via Turborepo)
pnpm install
pnpm dev / pnpm build / pnpm lint / pnpm lint:fix
pnpm test / pnpm typecheck / pnpm check   # check = lint + typecheck
pnpm format / pnpm format:check
pnpm docs:lint

# services/api (uv-managed)
uv sync
uv run fastapi dev app/main.py
make test / make test-verbose / make test-coverage
make test-integration   # hits real Delta Exchange — opt-in
make test-performance   # opt-in
make test-postgres      # requires TEST_DATABASE_URL
make db-upgrade / db-downgrade REV=-1 / db-current / db-history
make db-create-migration MESSAGE="..."

# infra
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml down     # add -v to also drop volumes
```

## Documentation Landscape

Read this before trusting any single doc file — quality is very uneven:

**Substantive and current** — trust these:

- `PROJECT.md` (vision/charter, ~85% real content, tail section is placeholder)
- `docs/architecture/*` (six of eight files — see table above)
- `docs/domain/MarketDataDomain.md` (real DDD entity model, written after implementation)
- `docs/api/API.md` (accurately documents the live API surface)
- `docs/DevelopmentSetup.md` (matches actual husky/commitlint/gitleaks setup)
- `services/api/README.md`, `services/api/TESTING.md`, `apps/dashboard/README.md`
- `infra/docker/README.md`, `configs/README.md`, `configs/environment.example.md`

**Empty templates (headers only, no content)** — do not treat as authoritative:

- Root `ARCHITECTURE.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `CHANGELOG.md`
- `docs/architecture/ARCHITECTURE.md`, `docs/ai/AI.md`, `docs/database/DATABASE.md`,
  `docs/deployment/DEPLOYMENT.md`, `docs/testing/TESTING.md`, `docs/decisions/DECISIONS.md`
- `apps/README.md`, `infra/README.md`, `packages/README.md`, `scripts/README.md`,
  `tools/README.md`, `tests/README.md` (all describe _intended_ future contents of
  currently-empty directories)

**Duplicated / conflicting pairs** (not yet consolidated — a judgment call for
the team, not made unilaterally during this discovery pass):

- Root `ARCHITECTURE.md` (empty, ~20 headings with placeholder text) vs
  `docs/architecture/ARCHITECTURE.md` (empty, 4 bare headings) — two different
  empty templates for what should probably be one document.
- Root `DECISIONS.md` (fully-designed ADR methodology, 198 lines, but an
  entirely empty decision index) vs `docs/decisions/DECISIONS.md` (11-line
  bare stub) — the root file is clearly the canonical one; the `docs/`
  version adds nothing.
- **Zero ADRs have actually been recorded** despite the ADR process being
  fully designed, and despite clearly ADR-worthy decisions already having been
  made in code (PostgreSQL, FastAPI, Next.js/MUI, uv, Delta Exchange as the
  primary venue, event-bus-over-message-broker, etc.).

**Fixed during this discovery pass**: `README.md`'s "Development Status"
section (previously claimed "Planning Phase... no application code has been
created yet", which was false); the two "OpenCode" references in
`TASKBOOK.md`'s workflow description (now say "Claude Code").

**Not changed** (flagged for the team to address deliberately, not fixed
silently): `TASKBOOK.md`'s progress tables (all tasks still show
Planned/Ready/0%, despite substantial completed work — the existing task IDs
don't map cleanly onto what was actually built, so relabeling them risked
inventing a task history rather than documenting one); the ARCHITECTURE.md and
DECISIONS.md duplication above; `docs/database/DATABASE.md` and
`docs/ai/AI.md` remain empty despite real database and (none yet) AI work.

## Notes for Future Claude Code Sessions

- This project was previously developed with OpenCode; Claude Code is now the
  primary assistant. No functional OpenCode artifacts remain to migrate.
- Always check `docs/architecture/EngineeringStandards.md` before introducing
  a new convention — it is detailed and current.
- Before adding a feature, check `docs/architecture/DomainModel.md` and
  `ContainerArchitecture.md` for the _intended_ bounded-context boundaries,
  even though most of them aren't implemented yet — new code should land in
  the right future home, not wherever is convenient today.
- Don't assume "WebSocket" means server push to the browser in this codebase
  — it currently only means the backend's outbound client to Delta Exchange.
  A real-time dashboard channel would require a new FastAPI WebSocket route.
- The formatting gate (`prettier --check .` / `ruff format --check .`) is
  currently failing repo-wide; running the corresponding `--write`/`format`
  command before a push is expected and matches existing tooling intent, not
  a scope-creeping cleanup.
- Root-level "status" documents (`README.md` Development Status,
  `TASKBOOK.md` progress tables, `DECISIONS.md` index) need active
  maintenance discipline going forward — they fell out of sync with
  `docs/architecture/*` and the service READMEs, which stayed accurate. Update
  the relevant status doc in the same commit/PR as any milestone-level change,
  per `TASKBOOK.md`'s own stated working rules.
