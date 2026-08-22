# Testing

## Purpose

Documents the platform's overall testing strategy across the backend
(`services/api`) and frontend (`apps/dashboard`) so a contributor knows
where a given kind of test belongs and how to run it.

## Status

Active — both services have real, enforced test suites and coverage gates.

## Overview

Each workspace owns its own test suite and tooling; there is no
cross-cutting end-to-end suite yet (`tests/` at the repo root is a reserved,
currently-empty placeholder — see its `README.md`).

- **Backend** (`services/api`): pytest + pytest-asyncio, run via `make
test`/`make test-coverage` (80% coverage gate) from `services/api`. Full
  detail — fixtures, markers, live-integration tests — lives in
  [`services/api/TESTING.md`](../../services/api/TESTING.md); this document
  does not duplicate it.
- **Frontend** (`apps/dashboard`): Vitest + Testing Library, run via `pnpm
--filter dashboard test` (or `pnpm test` from the repo root across all
  workspaces). Tests live next to the code they cover (`*.test.ts(x)`).

## Unit Tests

**Backend**: `services/api/tests/unit/`, `event_bus/`, `state_manager/`,
`processing/`, plus focused tests alongside `services/`, `repository/`
(SQLite-backed) — see `services/api/TESTING.md`.

**Frontend**: pure functions and Zod schemas are tested directly (no
rendering) — e.g. `src/types/api/market.test.ts`,
`src/features/markets/lib/quality.test.ts`, and the chart module's
`src/components/chart/data-adapter.test.ts` (OHLCV string→number
conversion, timestamp parsing, invalid/duplicate-candle handling) and
`chart-theme.test.ts` (MUI palette → lightweight-charts options mapping).

## Integration Tests

**Backend**: `services/api/tests/api/` (ASGI `httpx.AsyncClient` against
the real FastAPI app with an in-memory SQLite DB) and the opt-in
`tests/integration/delta/*` suite, which hits the **real** Delta Exchange
REST/WS API (`--run-integration`, never run by default).

**Frontend**: component tests render a feature page or module with its
real child components and only mock the network/API-client boundary —
e.g. `src/features/history/history-page.test.tsx` (mocks
`@/lib/api/market`), `src/components/chart/chart-container.test.tsx` and
`candlestick-chart.test.tsx` (mock `@/lib/api/market` and, since jsdom has
no real `<canvas>` 2D context, `lightweight-charts`'s `createChart` — see
"Testing the chart module" below). `src/components/chart/hooks/use-chart-candles.test.tsx`
exercises the real TanStack Query hook (via `renderHook` + `QueryClientProvider`)
against a mocked API client to verify pagination/truncation behavior.

### Testing the chart module

`lightweight-charts` draws to a `<canvas>` outside React's render cycle;
jsdom does not implement a real 2D rendering context, so every test that
mounts `CandlestickChart` (directly, or via `ChartContainer` /
`HistoryPage`) mocks the `lightweight-charts` module's `createChart` export
with a fake chart object (`addSeries`, `applyOptions`, `remove`,
`timeScale().fitContent`, `subscribeCrosshairMove`/`unsubscribeCrosshairMove`)
via `vi.mock('lightweight-charts', ...)`, keeping every other export
(`CandlestickSeries`, `HistogramSeries`, `ColorType`, `CrosshairMode`, …)
real via `importOriginal`. This verifies the component's _contract_ with
the library (series created once, data pushed on change, crosshair events
translated to OHLCV, cleanup on unmount) without needing a real canvas —
the library itself is TradingView's responsibility to test, not this
codebase's.

Covered this way: chart creation/teardown, pushing new data without
recreating the chart, fit-to-content on data change and on demand
(toolbar button), crosshair→legend translation, loading/empty/error states,
market/timeframe switching (re-fetch with new params), and a 10,000-candle
dataset through the full adapter pipeline (`data-adapter.test.ts`) to
confirm large datasets don't get silently truncated or reordered.

## End-to-End Tests

Not implemented. `tests/` at the repo root is reserved for this; no browser
automation (Playwright/Cypress) is configured yet.

## Performance Tests

**Backend**: `services/api/tests/performance/` (opt-in, `--run-performance`).

**Frontend**: no dedicated performance/benchmark suite. The chart module's
10,000-candle unit test (`data-adapter.test.ts`) verifies correctness at
that scale, not wall-clock render performance — see `FRONTEND.md` § "Chart
module → Performance considerations" for how large datasets are kept
smooth.

## Test Automation

Enforced locally via Husky (`.husky/pre-commit` runs `lint-staged`;
`.husky/pre-push` runs `prettier --check` and `markdownlint`) — see
[`DevelopmentSetup.md`](../DevelopmentSetup.md). **No CI/CD pipeline is
configured** (no `.github/` or equivalent exists in this repository), so
`pnpm test`/`pnpm lint`/`pnpm typecheck`/`pnpm build` (frontend) and `make
test`/`make test-coverage` (backend) must be run manually before every
push.
