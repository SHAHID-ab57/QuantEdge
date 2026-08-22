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
(SQLite-backed) — see `services/api/TESTING.md`. The market-stream
gateway's pub/sub logic is unit-tested the same way, without any
HTTP/WebSocket involved —
`services/api/tests/unit/marketdata/test_gateway.py` exercises
`MarketStreamGateway` directly (register/unregister, subscribe/unsubscribe,
symbol-scoped fan-out, snapshot generation, a full outbound queue dropping
a message rather than blocking). `TestWireTimestampFormat` in that same
file pins the outbound `event_time` wire format to a literal `Z` suffix —
regression coverage for a bug where a bare `datetime.isoformat()` (`+00:00`)
caused the frontend's `z.string().datetime()` schemas to silently reject
every trade/ticker/snapshot frame while heartbeat pongs kept the connection
looking healthy; see `src/types/api/market-stream.test.ts` for the matching
frontend-side pin, and `FRONTEND.md` § "Live Market Dashboard" for the full
story. Order-book reconstruction is unit-tested the same way, purely
against the event bus — `services/api/tests/unit/marketdata/test_orderbook.py`
exercises `OrderBookAggregator` directly: snapshot-replaces-book,
incremental-diffs-merge (upsert and zero-size-removes-a-level), `kind="l1"`
events never touching the reconstructed depth (regression coverage for the
exact corruption described above), sorting (bids descending/asks
ascending), depth limiting, and multi-symbol isolation. `TestOrderBookRelay`
in `test_gateway.py` covers the gateway's side: the fan-out relays the
_aggregator's_ reconstructed book (not a raw bus event), the snapshot
includes it, only subscribers of the affected symbol receive an update, and
a gateway built without an aggregator degrades to "no book" rather than
raising.

**Frontend**: pure functions and Zod schemas are tested directly (no
rendering) — e.g. `src/types/api/market.test.ts`,
`src/features/markets/lib/quality.test.ts`, the chart module's
`src/components/chart/data-adapter.test.ts` (OHLCV string→number
conversion, timestamp parsing, invalid/duplicate-candle handling) and
`chart-theme.test.ts` (MUI palette → lightweight-charts options mapping),
and the Live Market Dashboard's
`src/features/live-market/lib/aggregate-live-candle.test.ts` (client-side
candle bucketing/folding) and `lib/market-stream-url.test.ts` (derives the
gateway URL from `NEXT_PUBLIC_API_URL`, never the exchange).

Exchange-semantics assumptions are checked against the exchange, not
guessed: the trade-side mapping in `app/marketdata/normalizer.py` was
established by capturing the same fills from Delta's compact `trades`
channel and its verbose `all_trades` channel simultaneously and confirming
they agreed on all 55 matched trades. The unit test pins both directions of
the resulting mapping; the derivation is recorded in the constant's
docstring so a future reader can re-run it rather than re-guess.

## Integration Tests

**Backend**: `services/api/tests/api/` (ASGI `httpx.AsyncClient` against
the real FastAPI app with an in-memory SQLite DB) and the opt-in
`tests/integration/delta/*` suite, which hits the **real** Delta Exchange
REST/WS API (`--run-integration`, never run by default). The market-stream
WebSocket route is tested with Starlette's synchronous `TestClient`
(`tests/api/test_market_stream.py`) — protocol handling (subscribe/
unsubscribe/ping, snapshots, unknown actions, malformed JSON/payloads,
disconnect cleanup) against a fresh, per-test `Runtime` override, matching
the existing `tests/api/test_system_health.py` pattern. Concurrency-
sensitive bus-driven fan-out is deliberately _not_ re-tested at this layer
(cross-thread timing between the TestClient's ASGI portal thread and a
directly-awaited `bus.publish()` isn't a reliable place to assert on) — it
is fully covered at the gateway unit level instead (above).

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

### Testing market resolution and the live stream (frontend)

jsdom has no real network stack, so
`src/features/live-market/hooks/use-market-stream.test.ts` stubs the global
`WebSocket` constructor (`vi.stubGlobal('WebSocket', FakeWebSocket)`) with a
minimal fake exposing `send`/`close` and test-only `triggerOpen`/
`triggerMessage`/`triggerServerClose` helpers, combined with
`vi.useFakeTimers()` to drive the reconnect-backoff and heartbeat-ping
timers deterministically (no real waiting). This covers: subscribe-on-open,
trade/ticker/snapshot handling, schema-validation rejection of a malformed
frame, exponential backoff after a drop (capped, verified in a loop),
reconnect-attempt counting, symbol-change teardown/reopen, and no-reconnect-
after-unmount. Because updates are now batched rather than committed per message, every
assertion runs after a `deliver()` helper that fires the frame _and_
advances past the flush interval — asserting straight after
`triggerMessage` would race the flush instead of testing anything. The
batching itself is covered directly: a burst of twenty prints must land as
one commit, and a frame for a different symbol than the subscription must
be discarded entirely.

Market resolution is tested at two levels. The rules themselves are pure
functions with no rendering (`lib/market-selection.test.ts`,
`lib/timeframe-preference.test.ts`, `lib/remembered-market.test.ts` —
including storage that throws, as in private-mode browsers). The wiring is
tested through the page: `src/features/live-market/live-market-page.test.tsx`
mounts a catalogue whose alphabetically-first entry (`1000BONKUSD`) has no
candles and no live feed, and asserts the page resolves to `ETHUSD`
anyway, explains the substitution when one was explicitly requested,
honours a requested market that _does_ have data, restores a remembered
one, and persists its selection back to the URL.

That page test mocks `@/lib/api/market`, `@/lib/api/system` and
`lightweight-charts` as usual, and additionally fakes `next/navigation` —
the App Router that `useSearchParams` needs cannot be mounted in jsdom. The
fake is subscription-backed via `useSyncExternalStore` rather than a plain
getter, so a `router.replace` re-renders the page the way the real router
does; with a plain getter a market switch would write the URL and nothing
downstream would react to it.

### Testing the Order Book viewer (frontend)

`useMarketStream`'s order-book handling (the new `latestOrderBook` field,
the `orderbook` message type, and a snapshot's `orderbook` field) is
covered in the same `use-market-stream.test.ts` with the same
fake-WebSocket/`deliver()` pattern, plus a reset-on-symbol-change case
specific to the order book.

The depth/spread math is pure and tested with no rendering at all
(`lib/order-book-depth.test.ts`): cumulative-total accumulation,
`depthRatio` scaled against the deepest row _in the visible slice_ (not
the whole book), a 100+ level book truncated without artifacts, and
every spread field reporting `null` — never a misleading zero — when
either side of the book is empty. Component tests
(`components/order-book-table.test.tsx`, `spread-panel.test.tsx`,
`depth-selector.test.tsx`, `order-book-empty-state.test.tsx`) cover
column order (bids: Total/Size/Price; asks: Price/Size/Total), a 100-row
render, every `Unavailable` branch, and the retry action.

#### Testing the performance pass

Three mechanisms were added when the Order Book viewer was optimized for
high-frequency streaming, and each is tested at the level that actually
proves it, rather than through a full rendered page (which cannot
distinguish "the row's render function was skipped" from "it re-ran and
happened to produce identical output" — React reuses the same DOM node
either way):

- **`requestAnimationFrame` batching** — `use-market-stream.test.ts` spies
  on `globalThis.requestAnimationFrame`/`cancelAnimationFrame` directly
  (Vitest's fake timers fake both, so no real waiting is needed) to assert
  a single incoming message schedules exactly one frame, a ten-message
  burst still schedules only one, and a pending frame is cancelled on
  unmount rather than firing after teardown.
- **The `channels` option** — same file: a message on a disabled channel
  never updates the corresponding field _and_ never touches
  `lastMessageAt`/triggers a commit at all (verified by asserting the
  hook's state is untouched after delivering a disabled-channel message),
  while the enabled channel and heartbeat pongs still flow through
  normally.
- **Per-row memoization** — `order-book-table.test.tsx` unit-tests the
  exported `orderBookRowPropsAreEqual` comparator directly: two `DepthRow`
  objects with identical values but different references compare equal
  (the case that matters, since `computeDepthRows` never returns the same
  object twice), and a change to any one of price/size/total/depthRatio/
  side/color compares unequal. `React.memo`'s skip-the-render-when-equal
  behavior is a framework guarantee once this comparator is correct, so
  this is the precise, sufficient unit to test — not a render-count spy
  bolted onto the production component purely for testability.

`order-book-page.test.tsx` mirrors `live-market-page.test.tsx`'s
integration-test shape (same `next/navigation`/`FakeWebSocket` fakes) and
additionally asserts: bids render highest-to-lowest and asks
lowest-to-highest from a real (already-sorted, matching the gateway's
actual contract) fixture, the spread panel derives its numbers from the
streamed book, switching the depth selector re-slices without losing the
underlying 30-level book, an untracked explicitly-requested symbol is
honoured with an explanatory notice rather than silently substituted, and
a malformed `orderbook` payload is dropped without crashing the page.
Assertions that depend on a value arriving through the batched flush are
wrapped in `waitFor` rather than asserted immediately after `act()` —
the same real-timer-vs-flush-interval race the live-market stream tests
guard against.

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
