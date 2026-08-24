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

### Testing the Live Trade Analytics dashboard (frontend)

The math is exhaustively covered with no rendering and no timers at all:
`lib/session-stats.test.ts` (the O(1) accumulator folds correctly, is
pure — folding never mutates the accumulator passed in — and never
attributes an "unknown"-side trade to either side), `lib/rolling-window.test.ts`
(1m/5m/15m VWAP are independently correct re-filters of one buffer, a
record older than 15 minutes is excluded even if the underlying buffer
still holds it, and buy/sell imbalance is bounded to `[-1, 1]`),
`lib/ring-buffer.test.ts` (capacity is respected — the oldest entry is
overwritten, never silently grown past — and iteration order matches
insertion order across many wraps), `lib/sentiment.test.ts` (every
threshold boundary), `lib/trade-highlight.test.ts` (the large-trade
multiplier boundary), and `lib/metric-history.test.ts` (flattening
samples into per-metric arrays for the sparklines).

`engine/trade-analytics-engine.test.ts` tests `TradeAnalyticsEngine`
directly — no React, no rendering, no timers — proving `ingest`/`snapshot`
wire the pure functions above together correctly (an unparseable trade is
silently dropped, `reset()` clears every accumulator including the sample
history, sentiment is derived from the same rolling imbalance the numeric
tiles show, and a trade older than 15 minutes never leaks into the 15m
VWAP no matter how long the engine has run). Being framework-agnostic is
what makes this level of direct testing possible — see `FRONTEND.md` §
"Trade Analytics Engine."

`hooks/use-trade-analytics.test.ts` proves the hook _wires the engine up
correctly_ — every trade reaches it via `onTrade` (including a burst of
ten delivered in one tick), a symbol change resets it, sentiment and
sparkline history both update from streamed trades, and the tape stays
capped at `maxTapeRows` independent of the session count. This file
deliberately uses **real timers with `waitFor`**, not `vi.useFakeTimers()` —
`use-market-stream.test.ts` uses fake timers successfully, but this hook
additionally layers a real 1-second `useNow` tick on top of the rAF-batched
flush, and driving both mechanisms through `vi.advanceTimersByTime` in the
same test proved unreliable in practice (a scheduled commit would
intermittently not have landed before the next assertion despite `act()`
wrapping the advance, with the specific test affected varying run to run —
a genuine flakiness discovered and fixed during this feature, not a defect
in the hook itself, which a fully-isolated single-test run confirmed was
already correct). The one test that needs the wall clock to move without a
new trade arriving (rolling figures aging out during a quiet market) mocks
`useNow` directly and forces a re-render, rather than waiting on any timer
at all — deterministic, with no real waiting.

The quant-workstation pass (2026-08-23) added matching coverage for the
metrics it introduced: `lib/vwap-distance.test.ts` (null rather than
infinity for a zero VWAP, correct sign either side of it),
`lib/size-distribution.test.ts` (every trade lands in exactly one bucket,
shares sum to 1, an outsized print reaches the open-ended top bucket, and —
the property the design rests on — the same _shape_ of flow buckets
identically at any magnitude, so the panel needs no per-symbol
configuration), `lib/tape-export.test.ts` (metadata block, CSV quote
escaping, a blank rather than `NaN` value for an unparseable trade), and
`lib/metric-help.test.ts`, which asserts every entry in the contextual-help
dictionary is complete, written as full sentences (so a screen reader
announces prose), and short enough for a tooltip.

Component tests cover the dashboard's visual-hierarchy pass individually:
`sparkline.test.tsx` (a placeholder line with fewer than two known values,
`null` gaps skipped rather than plotted as zero), `buy-sell-pressure-bar.test.tsx`
and `market-sentiment-panel.test.tsx` (percentage split and chip color per
sentiment label), `largest-trade-card.test.tsx` (Time/Side/Price/Quantity/
Value all rendered, `Unavailable` before the first trade), and
`trade-tape-filters.test.tsx` (side toggle and minimum-size field). The
trade tape's own extensions are covered in `trade-tape.test.tsx`: a large
trade is marked at or above `largeTradeThreshold` and left alone below it,
and — the one test worth calling out — a pre-existing row's actual DOM
node (captured before a re-render, compared with `toBe` after) survives a
new trade being unshifted onto the front of the array, proving the
stable-per-trade-object key fix actually stops the whole table body from
remounting on every trade (the previous `${event_time}-${index}` key
scheme would have failed this test, since every row's index — and
therefore key — shifted on every new trade).

### Asserting render cost, not just render output

`trade-tape.render.test.tsx` is the unusual one: it measures **how many
components actually re-rendered**, which neither the DOM nor Testing
Library exposes — React reuses DOM nodes whether or not a component's body
re-ran, so node-identity assertions (above) catch remounts but say nothing
about wasted renders.

The technique is to spy on a formatter every row render calls a fixed
number of times (`formatDecimal`, mocked through to its real
implementation), turning call count into an exact row-render count. The
suite pins four properties: prepending one trade to a 100-row tape renders
**one** row rather than 101; a parent re-render with identical props
renders **zero**; a threshold change that newly flags a single row renders
**one**; and a virtualized 400-row tape renders a bounded window rather
than scaling with the list.

This is worth the indirection because it found a real bug that reads as
obviously correct in source: zebra-striping rows from their array index.
Prepending a trade shifts every index, flipping that prop for every row and
forcing a full re-render on each trade — 101 renders where one was
intended. Striping from the stable per-trade key instead fixed it. No
output-based test could have detected that, since the rendered stripes
looked identical either way.

`trades-page.test.tsx` mirrors the Order Book viewer's integration-test
shape and additionally asserts: the tape's Trade Value column
(price × quantity), statistics/VWAP/rolling analytics updating from
streamed trades, a market switch resetting every accumulator, the
max-rows selector changing the tape's cap, a Bullish sentiment chip
derived from one-sided buying, both Largest Trade cards showing the same
qualifying trade in full detail, the Buy filter narrowing the tape without
touching session statistics, the minimum-size filter, and the large-trade
highlight appearing only once a session baseline exists. The quant-
workstation pass added: current price / session high / session low /
VWAP distance in the primary band, the four labelled `region` landmarks
(Order Flow, VWAP, Session Statistics, Connection) proving the page is
grouped rather than flat, a representative Info button from every section
proving contextual help reaches each one, the size distribution rendering
over streamed trades, the "showing N of M rows" readout responding to a
filter, and the CSV export enabling only once rows exist.

Assertions read a specific `StatTile`'s value by walking from its
(unambiguous) label up to the nearest ancestor holding a value node,
rather than a bare `getByText` on the numeral — several tiles can
legitimately show the same number (e.g. buy volume and trade count both
being `2`), which a naive query would report as an ambiguous match. The
walk-up (rather than a single `parentElement` hop) is what keeps the
helper working now that each label shares a row with its Info button.

### Testing the Historical Market Replay Engine (frontend)

The engine layer has no React in it at all, so it is tested the same way
`TradeAnalyticsEngine` is — directly, with plain function calls and (for
the one piece with a timer) fake timers:

- `engine/replay-state-machine.test.ts` (47 tests) exhaustively covers
  every phase transition table entry, including the negative cases (an
  action that is a no-op for the current phase returns the exact same
  state reference, asserted with `toBe`) and the two behaviors this
  feature's own integration testing caught as genuine gaps during
  development, not anticipated up front: seeking onto the last candle now
  completes replay rather than leaving it paused with nothing left to
  advance to, and a retry after a failed load reuses the same request id
  and must be accepted from the `error` phase, not just `loading` —
  without that, a successful retry's `LOAD_SUCCESS` was silently ignored
  by the reducer's own phase guard and the page stayed stuck on the error
  screen forever, exactly the kind of bug a state machine's exhaustive
  transition tests exist to catch before a page-level test ever would.
- `engine/replay-scheduler.test.ts` (9 tests, fake timers) covers the
  self-rescheduling `setTimeout` chain directly: repeated ticks at a fixed
  interval, `setIntervalMs` changing the _next_ tick's timing without
  losing progress already made, idempotent `start()`, and a tick callback
  that stops the scheduler from inside itself without scheduling another.
- `engine/replay-timeline.test.ts` (17 tests) and `engine/replay-speed.test.ts`
  (6 tests) cover the pure timeline math (progress percentage, index ↔
  timestamp ↔ progress-percentage conversions, clamping) and the speed
  table respectively — both used directly by the reducer/hook and by the
  timeline/controls components, so a bug here would otherwise surface only
  indirectly through several component tests instead of one focused suite.

`hooks/use-replay-engine.test.ts` (17 tests) proves the React-facing hook
wires the reducer and scheduler together correctly — using fake timers
successfully and reliably, unlike `use-trade-analytics.test.ts`'s
real-timer workaround (see above): this hook has exactly one timer
mechanism (`ReplayScheduler`), not a rAF-batched stream layered under a
second wall-clock tick, which is what made fake timers unreliable there.
Covers: the full load lifecycle (including an empty result set and a
failed request), every control (play/pause/resume/stop/restart/next/
previous), speed changes not resetting the current index, seeking (both
directly by index and by progress percentage, including resuming playback
after a mid-playback seek), and that switching configuration (a new
request id) resets and reloads cleanly.

`hooks/use-replay-chart-sync.test.ts` (5 tests) proves the seed-vs-live-
candle split in isolation — a forward step at the same `revealEpoch`
leaves the seeded `candlesticks` array reference untouched (`toBe`), while
a `revealEpoch` bump produces a new one — and `replay-chart.test.tsx`
proves the same property end-to-end through the _real_ `CandlestickChart`
component (mocking only `lightweight-charts`, the same mocking pattern as
`candlestick-chart.test.tsx` itself): a forward step calls `series.update()`
without a second `setData()` call, while a restart calls `setData()`
again. `ReplayChart` reads its position from a `ReplayClockTick` prop
rather than raw `currentIndex`/`revealEpoch` fields (see below), so this
suite's fixtures build a tick object rather than passing those two values
directly — a mechanical change from an earlier version of this test file,
not a change in what's actually being verified.

#### Testing the Replay Clock and keyboard shortcuts

`engine/replay-clock.test.ts` (6 tests) tests `ReplayClock` directly — no
React — covering `getSnapshot`/`subscribe`/`publish` and, notably, that a
throwing subscriber is isolated: the clock's `publish()` catches and logs
a listener's exception rather than letting it stop the remaining
subscribers from being notified, mirroring the backend `EventBus`'s own
"handler failures never propagate" guarantee. `hooks/use-replay-clock.test.ts`
(3 tests) proves the thin `useSyncExternalStore` wrapper re-renders a
subscribed component on publish and unsubscribes on unmount.
`use-replay-engine.test.ts`'s "clock synchronization" block (5 additional
tests, 22 total in that file) proves the engine actually publishes to
this clock — the same instance across renders, a tick reflecting the
current candle after every advance, `isDiscontinuity` correctly `false`
for a plain forward step and `true` for a seek, and a live subscriber
notified on every scheduler-driven tick during auto-play, not just on
read.

`hooks/use-replay-keyboard-shortcuts.test.ts` (12 tests) covers every
shortcut in isolation with synthetic `KeyboardEvent`s: Space's three-way
branch (pause while playing, resume while paused, restart-via-play once
completed), Arrow/Home/End/+/- dispatching the right engine call, doing
nothing while `enabled` is `false` (no listener attached at all, not a
no-op handler), being skipped while focus is in a text field or inside a
focused `role="slider"` element, ignoring a modifier-held chord (e.g.
Cmd+Space), `preventDefault` on a handled key, and listener removal on
unmount.

`replay-page.test.tsx` (17 tests) is the integration suite: loading a
session end to end, an empty-result and a failed-request error state (the
latter with a working Retry action), playing/pausing/stepping, restarting,
seeking via the jump-forward control to completion, changing speed
mid-session without resetting position, switching market/timeframe/range
resetting to a fresh session, the enriched status panel's figures, the
timeline's jump-to-start/end buttons, and — driven through real
`fireEvent.keyDown(window, ...)` dispatches rather than calling engine
methods directly — every keyboard shortcut end-to-end, including that
typing in the config form does not trigger one. `replay-config-form.test.tsx`
(5 tests) separately covers the session-configuration form's Zod
validation (end before start, end in the future, all-fields-required)
using the same click-driven MUI `Select`/`Autocomplete` interaction
pattern as `HistoryForm`'s own tests — a MUI `TextField select`'s
interactive combobox element takes its accessible name from its
associated `<label>` via `aria-labelledby`, not from an `aria-label`
passed through `slotProps.select`, which only ever lands on a non-
interactive wrapper `div`; querying by the visible label text is what
actually resolves the right element.

`replay-controls.test.tsx`, `replay-timeline.test.tsx`, and
`replay-status.test.tsx` cover each control component in isolation —
notably that the Play/Resume toggle button shows "Resume" (not "Play")
whenever `phase === 'paused'`, since the two dispatch different actions
(`RESUME` only ever applies from `paused`; `PLAY` also applies from
`completed`, restarting at zero) even though their effect from `paused` is
identical — a subtlety the page-level integration tests must respect too
(clicking "Play" right after a fresh load fails, since the button reads
"Resume" at that point). `replay-controls.test.tsx` additionally proves a
MUI footgun did _not_ regress this feature: wrapping each speed
`ToggleButton` in its own `Tooltip` (added so every control has a tooltip)
risks the group's injected `selected`/`onChange` props landing on the
`Tooltip` wrapper instead of the button — a test asserts the correct
button still shows `aria-pressed="true"` and that clicking still fires
`onSpeedChange`, so a future MUI upgrade that changes this behavior would
be caught here rather than silently breaking speed selection.
`replay-status.test.tsx` (13 tests, up from 6) covers every new status-
panel figure — current/loaded/remaining candle counts, replay time,
speed, and estimated completion (including the boundary where it reads
"Unavailable" once `completed` versus "0s" once out of candles but still
`paused`/`playing`).

#### Asserting render cost with a targeted hook spy (Replay Engine)

`replay-page.render.test.tsx` proves the `ReplayConfigForm` memoization
fix precisely rather than by inference, using a variant of the "Asserting
render cost" technique above: it spies on `useTimeframes`
(`@/features/history/hooks/use-history-data`), which the form calls
unconditionally in its own render body. If `React.memo` bails out because
the form's props are unchanged, React does not invoke the component
function at all — so it does not call `useTimeframes()` again either,
turning "did the memo actually prevent wasted render work" into an exact,
assertable call count rather than an inference from DOM output that could
look identical whether or not the component actually re-ran. Three tests
cover: no additional calls across several manual `Next candle` clicks, no
additional calls during auto-play, and — proving the memo isn't
over-suppressing updates the form genuinely needs — a new call once the
form's own `disabled` prop actually changes. Removing the `React.memo`
wrapper during this review's own verification made the first two tests
fail immediately (11 expected calls vs. 17 and 13 observed), confirming
these are real regression guards rather than checks that would pass
either way.

## End-to-End Tests

Not implemented. `tests/` at the repo root is reserved for this; no browser
automation (Playwright/Cypress) is configured yet.

## Performance Tests

**Backend**: `services/api/tests/performance/` (opt-in, `--run-performance`).

**Frontend**: three dedicated performance suites, all fast enough to run in
the normal test pass rather than behind a flag.

`src/features/replay/engine/replay-engine.stress.test.ts` directly answers
the Replay Engine's "support 1/6/24 hours of replay data without freezing
the UI" requirement: it drives `replayReducer` through a simulated 1,440-
tick (24-hour, 1-minute-candle) session — plus `computeTimeline`'s own
per-tick recompute — and asserts the cost per tick stays flat rather than
growing, then separately confirms a 360-tick (6-hour) session completes
cleanly via the scheduler-driven `TICK` action. Building the candle array
once outside the loop (matching how a real session holds one stable
loaded array) rather than per iteration is what keeps this test itself
fast (~6ms) instead of accidentally measuring its own O(n²) setup cost.

`src/features/live-market/components/trade-tape.render.test.tsx` asserts
render counts directly — see "Asserting render cost, not just render
output" above.

`src/features/trades/engine/trade-analytics-engine.test.ts`'s sibling,
`trade-analytics-engine.stress.test.ts`, simulates a ~30-minute,
~12,000-trade sustained session by feeding synthetic timestamps to
`TradeAnalyticsEngine` in a tight loop (no real waiting — it runs in under
half a second) and asserts `ingest`/`snapshot` cost stays roughly flat
across the session rather than growing, which is exactly the property the
pre-ring-buffer implementation's O(n)-per-trade array copy would have
failed. This is a disclosed proxy for verifying stability over a long
streaming session, not a substitute for one: this environment has no
browser automation available to actually leave a tab open for 30 real
minutes and measure heap growth or paint timing, so that verification
remains outstanding — see `FRONTEND.md` § "Performance verification and
its limits." The chart module's 10,000-candle unit test
(`data-adapter.test.ts`) similarly verifies correctness at scale, not
wall-clock render performance — see `FRONTEND.md` § "Chart module →
Performance considerations" for how large datasets are kept smooth.

## Test Automation

Enforced locally via Husky (`.husky/pre-commit` runs `lint-staged`;
`.husky/pre-push` runs `prettier --check` and `markdownlint`) — see
[`DevelopmentSetup.md`](../DevelopmentSetup.md). **No CI/CD pipeline is
configured** (no `.github/` or equivalent exists in this repository), so
`pnpm test`/`pnpm lint`/`pnpm typecheck`/`pnpm build` (frontend) and `make
test`/`make test-coverage` (backend) must be run manually before every
push.
