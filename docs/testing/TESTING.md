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

### Testing the Technical Indicator Engine

**Backend.** The engine layer has no web or database dependency, so it is
tested directly — plain function calls, no fixtures, no ASGI:

- `tests/unit/indicators/test_params.py` (21 tests) covers coercion and
  validation. Values are passed as **strings** in most cases, because that
  is what the query layer actually delivers. Pins the decisions that
  matter: `"2.5"` is rejected for an `int` parameter rather than silently
  truncated, and an unknown parameter is rejected rather than ignored.
- `tests/unit/indicators/test_registry.py` (16 tests) covers the extension
  point. The load-bearing test registers a **brand-new indicator the
  registry has never seen** and resolves it, proving the "no engine change"
  claim rather than asserting it. Also pins duplicate rejection, that a
  class without `metadata` fails loudly, and that two registries share no
  state.
- `tests/unit/indicators/test_engine.py` (29 tests) covers the pipeline
  using **purpose-built stub indicators** — a `Doubler`, an `Exploding`, a
  `Misaligned`, an `Empty`, a `BadWarmup` — rather than the real SMA/EMA/
  RSI. That separation is deliberate: a change to a builtin's maths must
  never be able to make a pipeline test pass or fail for the wrong reason.
- `tests/unit/indicators/test_cache.py` (14 tests) covers the LRU and the
  fingerprint, including the one genuinely mutable case a naive fingerprint
  would miss: a still-forming final candle whose close changes while its
  open time does not.
- `tests/unit/indicators/test_builtin.py` (40 tests) covers discovery and
  correctness separately. Discovery asserts `load_builtin_indicators()` is
  idempotent (any entry point may call it defensively) and that every
  builtin publishes usable metadata — an indicator declaring no outputs
  would render an empty, unusable form on the frontend. Correctness checks
  each indicator against hand-computed values.
- `tests/unit/indicators/test_common.py` (8 tests) covers the shared
  moving-average utilities (`period_parameter`, `source_parameter`,
  `period_warmup`, `single_series_output`) independently of any indicator
  that calls them — so a bug in the shared factory can't hide behind
  SMA/EMA/WMA's own tests passing for unrelated reasons.

One RSI test is worth calling out because the **first version of it was
wrong**: an alternating +1/−1 series was asserted to sit at exactly 50.
Under Wilder's smoothing it does not — only the _seed_ is exactly 50, and
past that the newest change pulls it above or below. The fix pinned both
real properties (`the seed is exactly fifty` and `smoothing leans toward
the most recent change`), which is strictly more informative than the
original assertion would have been had it happened to pass.

**WMA's test class** (`TestWeightedMovingAverage`, 12 tests) is the
Trend Indicator Package's completeness check, covering every category the
task asked for: a hand-computed value against manually-weighted arithmetic
(not just "close to an SMA"), the warmup boundary, the `source` parameter,
a faster-than-SMA reaction after a price jump, a constant-price series
(every weighted combination of the same value must equal that value
exactly), an **empty dataset** (`InsufficientDataError` with the correct
required/available counts), an **invalid period** (zero and negative,
both `InvalidIndicatorParameterError`), and a **large dataset** — 5,000
candles cross-checked at four points against an independent, from-scratch
weighted-average computation written directly in the test (not just "it
didn't crash"). This test earned its keep immediately: a later
production-readiness review replaced WMA's O(n · period) naive
implementation with a true O(n) incremental one (see `ARCHITECTURE.md` §
"Complexity analysis"), and this exact cross-check is what verified the
faster algorithm still produces the same numbers — the two floating-point
paths agree to roughly 1e-9 relative error, well inside `pytest.approx`'s
default tolerance and irrelevant at the platform's six-significant-digit
display precision.

**The production-readiness review** added five more test classes to
`test_builtin.py`:

- `TestLargeDatasets` extends the same "not just fast, also correct at
  scale" discipline to SMA (cross-checked against a naive average at four
  points in a 5,000-candle series) and EMA (verified to stay finite and
  within the input data's own range over the same 5,000 points — the one
  indicator whose recursive formula could in principle drift or diverge).
- `TestRepeatedCalculationIsDeterministic` runs SMA, EMA, WMA, and RSI
  twice each on identical input and asserts bit-for-bit identical output —
  not a tautology: it would catch mutable shared state, a non-deterministic
  iteration order, or a cache bug that mutated a cached array in place. A
  dedicated test runs WMA once through a real `IndicatorCache` (a miss,
  then a hit) and confirms the cached path returns values identical to the
  freshly-computed ones — determinism has to survive the cache, not just a
  bare `calculate()` call.
- `test_every_builtin_publishes_complete_engineering_metadata` and
  `test_rejects_an_unsupported_price_source` close out the "every builtin,
  not just one" pattern the file already used for parameters/outputs.

`tests/unit/indicators/test_params.py` gained two tests for the new
"recommended default" bound-violation message: that it appears with the
spec's own declared default, and that it's omitted entirely for a
required parameter (which has no default to recommend).

`tests/services/test_indicators.py` (19 tests) exercises the service
against the in-memory SQLite database, so the ORM → `OHLCVPoint`
projection and the shared market/timeframe/range/limit validation are
covered against real rows — including
`test_calculates_correctly_when_optional_candle_fields_are_null`, which
pins that a candle's nullable `quote_volume`/`trade_count` fields (never
read by the projection) can't affect a calculation, and
`test_publishes_engineering_metadata_for_every_indicator`, which checks
the new `version`/`author`/`complexity`/`warmup_description` fields
reach the service layer's DTOs. `tests/api/test_indicators_api.py`
(24 tests) covers the REST surface end to end over ASGI, including that
indicator parameters really are collected from the raw query string,
that the new metadata fields serialize correctly, that an out-of-range
parameter's error message recommends the declared default, that timestamps
serialize with a literal `Z` suffix (the frontend's
`z.string().datetime()` rejects a `+00:00` offset — the same bug the
market-stream gateway once shipped), a full WMA calculation against
hand-computed weighted values over real stored candles, and every error
code the endpoint can produce.

**Frontend.** `lib/parameter-values.test.ts` (19 tests) covers the pure
form helpers, including the two decisions most likely to be "simplified"
later: a required parameter seeds to blank rather than a plausible zero,
and an omitted optional parameter is dropped rather than sent as `""`
(which the backend would reject as an invalid int instead of applying its
default).

`components/parameter-form.test.tsx` (15 tests) proves the form is
genuinely spec-driven by rendering **arbitrary specs the codebase has never
seen** (`alpha`, `beta`) and asserting the declared bounds land on the
input as `min`/`max`, plus the enrichment layer added in the usability
review: a curated per-parameter tooltip when the knowledge base has one, a
fallback to the backend's own `description` when it doesn't, and a
recommended-value chip per curated preset that writes straight to the
field on click.

**The indicator knowledge base and result analysis are both pure and
independently tested**, deliberately separate from any component:
`lib/indicator-knowledge.test.ts` (11 tests) pins the curated content for
`sma`/`ema`/`wma`/`rsi` (formula, chart config, RSI's 30/50/70 thresholds
and classifier) and — the more load-bearing half — that an indicator the
knowledge base has never seen still gets a complete, honest fallback
(a real purpose from the catalogue description, an explicit "not yet
documented" for the formula/advantages/limitations, never a fabricated
one). `lib/result-analysis.test.ts` (21 tests) covers `summarizeSeries`:
latest/previous extraction across trailing nulls, absolute/percentage
change (including a zero-previous guard against dividing by zero), trend
direction, and — since a production-readiness review corrected an
earlier design mistake here — the deliberate **absence** of a fabricated
state for a plain trend indicator (`summary.state` is `null` for SMA/EMA/
WMA; only RSI's own threshold-based classifier produces one), plus
`summary.status` (`'computed'` vs. `'warming-up'`). The review's own
before/after: `classifySignal` returning generic `'bullish'`/`'bearish'`
labels synthesized from mere trend direction was renamed to
`classifyState`, which now only ever returns a value when the indicator
itself defines one (RSI: `"Overbought"`/`"Oversold"`/`"Neutral"`,
describing where the oscillator sits, not a reading of what to do about
it) — this platform displays analytical information, never a trading
signal, and the test suite pins that distinction explicitly rather than
leaving it to a docstring.

`components/indicator-chart.test.tsx` (6 tests) covers the SVG
visualization: one path per series, legend swatches, oscillator reference
lines, and the "not enough data" placeholder when nothing can be drawn.
Reference-line coloring uses a purely positional `band` (`'low'`/`'mid'`/
`'high'`) rather than the removed bullish/bearish `tone`, mapped to
neutral `info`/`warning`/`divider` colors instead of this codebase's
"good/bad" success/error green/red — a chart threshold line is not a buy/
sell cue. `lib/svg-line-path.test.ts` (14 tests) covers the underlying
domain/path math shared with the Trade Analytics `Sparkline` — including
that a `null` mid-series is skipped rather than plotted as a zero-value
point, and that a zero-range domain centers its line instead of dividing
by zero.

`components/result-summary.test.tsx` (12 tests) covers the expanded
results summary: change/trend, that a plain trend indicator shows **no**
state badge at all (the corrected behavior above), RSI's Overbought/
Oversold badges, the `Status: Computed`/`Status: Warming up` line, and —
new in this review — Current Price and Distance-from-Current-Price rows
that only render once a `currentPrice` prop is supplied. `lib/current-
price.test.ts` (4 tests) covers `extractCurrentPrice`'s field selection
(matching the indicator's own resolved `source` parameter, falling back to
`close` for an indicator with none or an unrecognized value) — kept as a
pure function so the "which field did we compare against" logic is
tested without a network mock. `components/indicator-metadata-card.test.tsx`
(11 tests) covers the engineering metadata card, now sourcing category,
time complexity, warmup description, version, and author straight from
the backend's own `IndicatorMetadata` fields rather than the hardcoded
`"O(n)"` / `"Not exposed by the API"` placeholders an earlier version of
this card used — and that "Supported Price Sources" is derived from the
`source` parameter's `choices`, not a second hardcoded list.
`components/indicator-info-panel.test.tsx` (9 tests) covers the
collapsible research card, including its own graceful degradation for an
uncurated indicator. `components/field-info.test.tsx` (3 tests) covers
the shared ⓘ tooltip affordance.

`components/export-menu.test.tsx` (7 tests) covers CSV/JSON download (via
mocked `URL.createObjectURL`/`revokeObjectURL`), clipboard copy for both
values and the literal API request URL (mocked `navigator.clipboard`),
and a clipboard failure reporting itself rather than failing silently.
`lib/export.test.ts` (15 tests, up from 11) adds coverage for the
knowledge-base-enriched export: a CSV/JSON export without a `knowledge`
argument says the formula is "Not available" rather than omitting the
field silently, and one with it includes the formula and purpose inline —
additive to the raw calculation response, never replacing a field it
already carries. `lib/recent-calculations.test.ts` (10 tests) covers
localStorage persistence, including a corrupted-JSON value, a non-array
value, and a throwing `Storage` (private browsing, quota), all tolerated
without surfacing an error to the researcher.
`components/recent-calculations-panel.test.tsx` (6 tests) covers the list
UI, including both of its two independent rerun triggers (the row itself
and its dedicated button).

`components/indicator-results.test.tsx` (11 tests) covers the composed
results view — summary, chart, metadata stat tiles, and the values table —
including that trailing nulls are skipped when reporting the latest value
and that a fully-null series renders an em dash rather than a misleading
zero.

`indicators-page.test.tsx` (26 tests) is the integration suite: catalogue
loading and error states with a working retry, the form rebuilding from
the selected indicator's specs, **reseeding when the indicator changes**
(carrying SMA's period 20 into RSI would silently calculate something the
researcher never asked for), that a calculation fires only on submit and
not on every keystroke, that client-side validation blocks a bad value
without calling the backend at all, the calculating/error states, that
Current Price and Distance resolve once the market's latest-candle lookup
(mocked `fetchLatestCandle`, reused from the History feature's existing
endpoint rather than a new one) completes, the
information panel appearing (and degrading gracefully for an uncurated
indicator), the metadata card's live cache status, the export menu
appearing only once a result exists, and recent-calculation recording plus
**one-click rerun** — proven by two configurations that produce
distinguishable results, rather than asserting the mock was re-invoked
(rerunning an identical, still-fresh configuration is correctly served
from the query cache with no network call, which the test treats as
correct rather than a failure).

**Shared-infrastructure promotions were verified against their original
suites, not just the new one.** This review promoted four small primitives
out of features that already had them, once the Technical Indicators page
needed the identical behavior: `MetricInfo` → `InfoTooltip`
(`src/components/info-tooltip.tsx`), `Sparkline`'s path math →
`src/lib/svg-line-path.ts`, the History export module's CSV escaping →
`src/lib/csv.ts`, and its download-a-blob helper → `src/lib/download-file.ts`.
Every one of `trades/`'s and `history/`'s existing test files (201 and 18
tests respectively) was re-run after each promotion and passed unmodified —
the promotions are refactors of _where the logic lives_, not changes to
what it does.

### Testing the Dataset Validation usability pass

This pass added no backend change at all, so every new test is frontend-
only (`apps/dashboard/src/features/dataset-validation/`,
`.../feature-engineering/`). It follows the same layering the rest of this
document already uses: pure logic tested with no rendering, then
components, then the page.

**Pure logic, no rendering.** `lib/resolve-required-columns.test.ts`
covers `columnCategoryFor` (every backend category mapped to its UI
bucket, and the "Future Features" fallback for one this map doesn't
recognize — the same graceful-degradation discipline `groupByCategory`'s
own tests already establish), `resolveRequiredColumnOptions` (a
parameterized output resolves against a feature's _selected_ parameters
when it's part of the current selection and its _published defaults_
otherwise, and a column produced by more than one feature is deduplicated
once), and `resolvePresetFeatures` (each of the five presets against a
small fixture catalogue, including one that resolves to an empty set when
nothing matches). `lib/quality-score.test.ts` pins the exact heuristic (15
per error, 5 per warning, floored at 0, informational findings never
counted) and every `qualityBand` boundary. `lib/rule-knowledge.test.ts`
asserts every one of the eleven builtin rules has curated content
(including a literal pin of the `duplicate_rows` copy this feature's own
spec specified verbatim), that an uncurated rule name degrades to an
honest "Not yet documented" rather than an error, and the same for
`suggestedFixFor`'s per-`code` fallback — mirroring
`indicator-knowledge.test.ts`'s exact curated-plus-fallback assertion
shape, applied to rules instead of indicators.

**Stores.** `use-recent-columns-store.test.ts` mirrors
`use-recent-features-store.test.ts` test-for-test (front-of-list
recording, dedup-by-moving-to-front, an eight-entry cap, clearing) —
expected, since it's the identical `persist`/`sessionStorage` pattern
applied to column names. `use-favorite-features-store.test.ts` is the one
store in this codebase deliberately tested _without_ clearing
`sessionStorage` in its `afterEach` — it persists to `localStorage`
instead, and the test suite clears that store explicitly to match.

**Components.** `feature-selector.test.tsx` gained four new `describe`
blocks for the additions shared by both `FeatureSelector` callers:
metadata display (each row's `v{version} · {category} · {N} columns`
caption), favorites (star toggle, `aria-pressed`, the quick-pick chip, and
a persistence-across-remount check proving `localStorage` survival),
expand/collapse (per-category and bulk Expand All/Collapse All, plus a
keyboard-navigation test proving Arrow-key focus skips a collapsed
category's now-hidden rows), and select-all/clear-all (respecting an
active search filter for Select All, ignoring it for Clear All, and
disabled-state checks for both). `dataset-form.test.tsx` is a new,
dedicated file — the component had grown enough new logic (a tooltip
beside every field) to warrant direct coverage rather than relying only on
the page-level tests that already exercise it — and its one load-bearing
test asserts a tooltip **never changes** the field's pre-existing
`aria-label`/`label` text, since two other pages' tests already query
those fields by exactly those strings.

`required-columns-selector.test.tsx` and `required-column-presets.test.tsx`
are new. The former covers the MUI `Autocomplete`
(`multiple`+`freeSolo`+checkboxes+`groupBy`) end to end: opening it lists
every resolved option grouped by category, search filters them, selecting
an option commits its name, a selected feature's own chosen parameters
(not its defaults) resolve into the option list, typing an arbitrary name
and pressing Enter still commits it (the preserved `freeSolo` escape
hatch), and Select All/Clear All/the recently-used row all behave as
expected. `validation-rule-catalog.test.tsx` and
`validation-issue-list.test.tsx` were both extended for their new
expand/collapse behavior (each degrading gracefully for uncurated content,
per the pattern above) and — `validation-issue-list.test.tsx` specifically
— the Copy Issue button, using a mocked `navigator.clipboard.writeText`
since jsdom does not implement the Clipboard API. `validation-report-panel.test.tsx`
is new and covers the consolidated search/severity-filter/category-filter/
expand-all/export-issues panel, including that toggling a severity chip
off and back on is reversible and that "Export Issues" only serializes the
currently-filtered subset. `validation-summary-cards.test.tsx` was
extended for the new dataset-shape cards and the Quality Score, scoping
assertions to a specific card's container (`getByText(label).closest(...)`)
rather than a bare `getByText(value)` wherever a numeral could otherwise
collide with an unrelated card showing the same figure.

**A recurring gotcha, worth naming explicitly: MUI's `Collapse` with
`unmountOnExit` does not remove its content from the DOM synchronously.**
Its exit transition — even in jsdom, which has no real CSS — still runs
through an asynchronous fallback timeout before the child unmounts, so a
test that fires a collapse-triggering click and immediately asserts
`.not.toBeInTheDocument()` will intermittently see the _pre-collapse_ DOM.
Every test in this pass that collapses something (a Feature Selector
category, a rule catalogue row, an issue row) wraps that specific assertion
in `await waitFor(...)` rather than asserting synchronously — expanding
(entering) never has this problem and is asserted directly.

**Page-level.** `dataset-validation-page.test.tsx` was substantially
rewritten: the old free-text "type a comma-separated string" test is
replaced with driving the real `Autocomplete` (open it, click an option),
a new test proves applying a preset seeds both the feature selection and
the required-columns selector correctly (asserting the actual outgoing
request, not just DOM state), the two old fixed "Errors"/"Warnings"
section assertions collapsed into one "Validation Report" section check,
and a new empty-state test asserts the "What validation does"/"How to
start"/"Example workflow" copy renders before anything has been validated.

### Testing the ML Dataset Builder (frontend)

`apps/dashboard/src/features/ml-datasets/` follows the same layering as
every other feature module in this document: pure logic tested with no
rendering, then components, then the page. A second, UX/reproducibility-
focused pass (searchable target selection, horizon presets, a split
timeline, dataset metadata, configuration copy/import, and an export
confirmation dialog) added tests the same way, with no backend involved
in any of them.

**Pure logic, no rendering.** `lib/target-selection.test.ts` mirrors
`feature-selection.test.ts` test-for-test (defaulting a selection's
parameters from the catalogue's published defaults, toggling a target in
and out while preserving the order of the rest, replacing one selection's
params without touching any other, mapping selections onto the API request
shape) — expected, since it is the identical selection-state contract
applied to targets instead of features. `lib/split-ratios.test.ts` pins the
exact tolerance (`1e-6`) the client-side check shares with the backend's
own `ChronologicalSplitter._validate_ratios`, including the IEEE-754
`0.7 + 0.15 + 0.15` case that is not bit-exact in floating point, so a
form that "looks like it sums to 1.0" is never rejected by a stricter
client-side check than the server actually enforces. `lib/horizon-presets.test.ts`
covers preset filtering against a target's declared min/max bounds and the
"Custom…" sentinel resolution. `lib/target-type.test.ts` pins the
`value_type` → Classification/Regression mapping and the horizon-range
description text, including its fallback for a target with no `horizon`
parameter at all. `lib/export-format.test.ts` covers the byte-size
heuristic (including that it scales with the extra `split` column) and
`formatBytes`'s unit rounding. `lib/dataset-config.test.ts` is the
round-trip test that matters most in this pass: it serializes a
configuration and asserts `parseDatasetConfig` reconstructs the identical
object, plus invalid-JSON, missing-required-field, and wrong-type-field
rejection cases with actionable error messages.

**Components.** `split-config-form.test.tsx` covers the three ratio fields
rendering their current values and percentage helper text, the
valid/invalid state toggling the `SplitTimeline` versus an error message,
editing a field calling `onChange`, and that an estimated per-split row
count only appears once `estimatedTotalRows` is supplied (i.e., only after
a dataset has actually been built). `target-selector.test.tsx` drives the
`Autocomplete` search box directly (opening it, narrowing by search text,
reading an option's problem-type chip/description/output/horizon-range
text, selecting and removing a target via its tag and via its card's
remove button) and separately exercises `HorizonPresetSelect` (seeded
value, committing a preset change, and revealing/using the "Custom…"
field) — the horizon commit tests assert against the visible "Horizon"
label rather than a supplementary `aria-label`, since `getByLabelText`
resolves an MUI `Select`'s programmatic `aria-label` to its outer
`InputBase` wrapper rather than the inner interactive `role="combobox"`
element, and only the visible-label route lands on the element `mouseDown`
needs to actually open the menu. `export-summary-dialog.test.tsx` and
`dataset-config-actions.test.tsx` are new, covering the confirmation
dialog's rows/columns/target/split/format/approximate-size display and,
respectively, clipboard copy (asserting the exact round-tripped JSON,
degrading silently on a rejected `navigator.clipboard.writeText`) and
paste-to-import (valid JSON restoring state, invalid JSON surfacing an
inline error, Cancel discarding the pasted text). `ml-dataset-export.test.tsx`
was rewritten around the new confirm-then-export flow: clicking a format
button opens the dialog without exporting, Cancel discards it without
exporting, and only confirming the dialog triggers `downloadBlob`.
`ml-dataset-metadata-panel.test.tsx` is new, pinning the dataset UUID,
source market/timeframe/date-range, generated timestamp, the "Validation
Report ID" honestly reusing the embedded report's own `dataset_id`, the
target-generator list, and the fixed `ChronologicalSplitter` label.

**The shared preview table gained tests for its new, optional behavior
without touching any of its existing assertions.**
`dataset-preview-table.test.tsx` (Feature Engineering's own test file — not
forked, since the component itself was extended, not duplicated) gained
`describe` blocks for: the target-column badge and the "Split" column
(unchanged from the first pass); column search (narrows the rendered
columns, reports when nothing matches); the column-visibility menu
(hides/re-shows a column, and resets whenever the dataset's own column
list changes shape — proven by rerendering with a differently-shaped
dataset while a column is hidden); the sticky Timestamp column (asserting
its computed `position: sticky; left: 0` style); and `ColumnStatsPopover`
(offered only for numeric columns, showing computed min/max on open, and
noting when the figures are preview-scoped because `maxRows` capped the
table). Several of these assertions scope their queries to
`document.querySelector('table')` via `within(...)` rather than the whole
document, since MUI's `Menu`/`Popover` marks the rest of the page
`aria-hidden` while open and can otherwise leave a stale, still-open menu
item's text colliding with the table's own.

**Page-level.** `ml-datasets-page.test.tsx` mirrors
`feature-engineering-page.test.tsx`'s structure section-for-section
(loading/error states, configuration, building, export) with the additions
this page's own requirements demand: the build button stays disabled until
both a feature _and_ a target are selected (two independent empty-selection
messages, not one), and separately disables when the split ratios don't sum
to `1.0` even though a feature and target are both selected; target
selection is driven through the `Autocomplete` (`selectNextClosePrice`
helper) rather than a checkbox, matching the rewritten `TargetSelector`;
the outgoing request is asserted to carry `targets` and
`split_train`/`split_validation`/`split_test` alongside the existing
`features` field; a built dataset's preview is asserted to render the
"Split" column (queried by `getByRole('columnheader', ...)` specifically,
since the info card also renders the literal word "Split" elsewhere on the
page and a bare `getByText` collides); export is asserted to open the
summary dialog before calling the backend, and only export after
confirming; a new `describe` block covers the metadata panel appearing
once built and the Copy/Import Configuration controls, including a full
paste-and-restore round trip; and a target-generation partial failure is
asserted to render in the summary without blocking the rest of the
dataset from displaying, mirroring the equivalent feature-failure test in
the Feature Engineering suite. This file's own `testTimeout` is raised to
15s (`vi.setConfig`) — its tests each drive two `Autocomplete`s and a full
page render, which occasionally exceeds the default 5s only under the
full suite's parallel worker contention, never when the file runs alone.

### Testing the Experiment Management System (frontend)

`apps/dashboard/src/features/experiments/` is this platform's first
dynamic route and its first page built around persistent, full-CRUD
backend state, so its own test suite follows the usual layering (pure
logic, then components, then the two composition roots) with one added
wrinkle: several MUI accessibility-query gotchas that hadn't come up in
any prior feature's tests.

**Pure logic.** `lib/experiment-status.test.ts` pins the status→label
capitalization and the color mapping for every status, including that
`statusLabel` accepts an arbitrary string (not just a known status) since
the filter bar's status list comes from the backend's own
`ExperimentListResponse.statuses`.

**Components.** `experiment-filters-bar.test.tsx`,
`experiment-notes-card.test.tsx`, `experiment-metrics-table.test.tsx`,
`experiment-artifacts-list.test.tsx`, and `delete-experiment-dialog.test.tsx`
each cover one interactive component in isolation — search/status/tag
filter changes, the notes view/edit toggle, the metrics and artifacts
inline add forms (including that Add stays disabled until the required
fields are filled, and that unit/description default to `null` rather
than an empty string), and the delete confirmation dialog's busy state.

**Two new MUI query-scoping gotchas, worth naming so a future test
doesn't rediscover them the slow way:**

1. **`getByLabelText` matches a `<section>` via `aria-labelledby`, not
   just a form control's own `aria-label`.** Every `Section` component
   renders `aria-labelledby` pointing at its heading, so
   `screen.getByLabelText('Notes')` matches _both_ the whole Notes
   `<section>` (labelled by its own "Notes" heading) _and_ the notes
   `<textarea aria-label="Notes">` inside it — "multiple elements found."
   The fix is scoping: query a more specific `aria-label` first (e.g. the
   wrapping `Stack`'s `"Edit experiment notes"`) and find the actual
   control with `within(...).getByRole(...)`, rather than reaching for the
   generic field name directly.
2. **An MUI `Select`'s own `aria-label` lands on the outer `InputBase`
   wrapper, not the inner interactive `role="combobox"` div `mouseDown`
   needs to actually open the menu** — the same gotcha the ML Dataset
   Builder's `HorizonPresetSelect` tests already ran into. Where a visible
   MUI `label` prop exists, query by that (it resolves to the correct
   inner element); where it doesn't (`ExperimentMetadataPanel`'s status
   select has no visible `label`, only an `aria-label`), scope with
   `within(screen.getByLabelText(...)).getByRole('combobox')` instead.

**Page-level.** `experiments-page.test.tsx` covers the list page: loading/
error/empty states, search/status-filter/sort all producing the expected
outgoing `fetchExperiments` call, and the create-experiment flow
(disabled until a name is entered, calls `createExperiment`, navigates to
the new experiment's detail page on success). `experiment-detail-page.test.tsx`
covers the detail page: loading/error states, metadata display (including
the feature set/target/split configuration read from the nested JSON
fields), the status select calling `updateExperiment`, notes edit-and-save,
a tag addition sending the full replacement tag set, metric and artifact
add/delete each calling their own endpoint with the experiment id, and the
delete-experiment confirm/cancel flow (confirming navigates back to
`/experiments`; cancelling calls nothing).

### Testing the Machine Learning Training Framework (frontend)

`apps/dashboard/src/features/ml-training/` follows the same layering as
`experiments/`: pure logic, then components in isolation, then the two
composition roots (the list page, and the two dialogs it opens). The
usability pass (tooltips, searchable comboboxes, auto-population, the
summary panel, the stage timeline, the improved logs panel, confirm
dialogs, and proactive validation) added several new focused component
test files rather than growing the existing ones.

**Pure logic.** `lib/training-job-status.test.ts` pins the status→label/
color mapping, the stage→label mapping (`STAGE_ORDER`, the single source
of truth both the log panel's stage badges and the stage timeline read
from — a deliberate fix: these two once had their own, differently-worded
copies of the same six labels), and the fallback for a stage the frontend
doesn't recognize. `experiment-metadata-panel.test.tsx` (in `experiments/`,
not `ml-training/` — see below) covers `describeFeatureSet`/
`describeTargetConfig`/`describeSplitConfig`/`describePredictionHorizon`.

**Components.** `hyperparameter-editor.test.tsx` covers the known-field
numeric validation (integer/bounds/blank-means-omitted for `epochs`/
`learning_rate`/`batch_size`/`random_seed`/`validation_frequency`, each
with its own default), the custom key/value list (add/edit/remove, and
that a custom name colliding with a known field is rejected with an inline
warning rather than silently overwritten), and the
`buildHyperparametersPayload`/`coerceHyperparameterValue`/`entriesToRecord`/
`recordToEntries`/`knownHyperparametersAreValid` helpers.
`training-job-filters-bar.test.tsx` covers the experiment/status filter
dropdowns. `training-job-stage-timeline.test.tsx` asserts all eight steps
always render, the correct step carries `aria-current="step"` while
running, no step is "active" once the job is `pending`/`completed`/
`failed`, and a failed job's failing stage is marked without implying
later stages ran. `training-job-logs-panel.test.tsx` covers search
filtering, copy (mocking `navigator.clipboard.writeText`), download being
disabled with no logs, and collapse/expand (which needs an explicit
`waitFor`/`findBy*` — MUI's `Collapse` unmounts its content asynchronously
even with `unmountOnExit`, so a synchronous `queryBy*` right after the
click still sees the old content). `training-summary-panel.test.tsx`
covers every warning chip appearing when a field is unselected and the
correct values once an experiment is supplied.
`confirm-action-dialog.test.tsx` and `empty-state-notice.test.tsx` (now
`src/components/`, promoted out of this feature once Dataset History and,
later, the Model Evaluation & Benchmarking page needed the identical
patterns) cover the two small generic components each in isolation.

**Two MUI gotchas specific to this feature, worth naming:**

1. **A required MUI `TextField select`'s visible asterisk becomes part of
   the associated `<label>`'s accessible name in this MUI version.** The
   create dialog's Model Type field was originally a `TextField select`;
   `getByLabelText('Model type')` (an exact match) failed until the
   field's `aria-label` was set explicitly via
   `slotProps={{ select: { 'aria-label': 'Model type' } }}` — the same fix
   `experiments`' own required-field tests already needed for a plain
   `TextField`, just here needed for a _select_ specifically. Model Type
   was subsequently rewritten as a searchable `Autocomplete` (per the
   comboboxes requirement); its `renderInput` `TextField` still carries
   the same explicit `aria-label` override, but now resolves to a real
   `<input>` element — so `toHaveValue('Placeholder Model')` works
   directly, unlike the old native select (which required
   `toHaveTextContent` instead, since MUI's `Select` shows its display
   text in a `div[role="combobox"]`, not a real `<input>`).
2. **`Tooltip`-wrapped `IconButton`s render their `aria-label` on both the
   `Tooltip`'s cloned wrapper `<span>` and the inner `<button>`** when the
   button is disabled (a disabled element can't receive the pointer
   events a `Tooltip` needs, so MUI wraps it in a forwarding `<span>`) —
   `getByLabelText`/`getByText` then finds two matches. `training-job-logs-panel.test.tsx`'s
   disabled-copy/download assertions and the "copies logs" test query
   `getByRole('button', { name: ... })` instead, which resolves to the
   inner `<button>` unambiguously.

**Page-level.** `ml-training-page.test.tsx` covers the list page (loading/
error/empty states — including "no experiments exist yet" versus "no jobs
match this filter" — experiment/status filtering, sorting), the create-job
dialog (proactive validation messaging that updates live and disappears
once every required field is filled; the Experiment Autocomplete
auto-filling Dataset Version from the selected experiment; the empty-state
notices for zero experiments, zero recorded dataset citations, and zero
model adapters; and successful creation opening the detail dialog), and
the detail dialog (the stage timeline, the log trail, the result summary
once completed, the error message on a failed job, and the Run action plus
the confirm-then-mutate flow for both Cancel and Delete — including
backing out of a confirmation without triggering the mutation). The
Experiment selector appearing in both the page's filter bar and the create
dialog at the same time (once the dialog is open) means tests querying
"Experiment" scope with `within(screen.getByRole('dialog'))` rather than
the bare `screen`, to avoid a "multiple elements found" ambiguity — the
same scoping discipline `experiments`' own tests already established for a
different ambiguity.

**Baseline Model Framework additions.** The Baseline Model Framework work
(scikit-learn Logistic/Linear Regression adapters behind the existing
`ModelAdapter` registry) added a dedicated component test file plus new
cases in the existing page-level suite, rather than growing unrelated
files.

`evaluation-summary.test.tsx` covers the new `EvaluationSummary` component
in isolation: it renders a confusion matrix and classification metrics
(accuracy/precision/recall/f1) for a `model_kind: 'classification'` result,
renders a plain metrics table (mae/mse/rmse/r2) with no confusion matrix
for `model_kind: 'regression'`, and falls back to a generic metrics table
for the `placeholder` kind or an adapter the frontend doesn't recognize —
using the same `isNumberMatrix`/`isStringArray` type guards the component
itself uses, so a malformed metrics payload degrades to the generic table
instead of throwing.

`ml-training-page.test.tsx` gained a `vi.mock('@/lib/api/market', ...)`
alongside its existing `@/lib/api/experiments` and `@/lib/api/training`
mocks, stubbing `fetchMarkets`/`fetchTimeframes` the same way the Markets
and History pages' own tests already do. New cases in the create-dialog
suite: the Configuration panel (Symbol/Timeframe/Target column) only
appears once a `requires_real_data` adapter is selected — choosing the
placeholder adapter again hides it; Symbol and Timeframe are validated as
required whenever the panel is visible; selecting a Symbol populates the
Timeframe options from `fetchTimeframes` for that market; and a full
real-data submission (Logistic Regression, a symbol, a timeframe, and a
target column) is asserted against the exact `symbol`/`timeframe`/
`target_column` values sent to `createTrainingJob`. New cases in the
detail-dialog suite render a completed job whose result carries
classification metrics and assert the confusion matrix and its labels
appear, and separately render one with regression metrics and assert the
plain metrics table appears with no confusion matrix — exercising
`ResultSummaryCard`'s use of `useModelAdapters()` to resolve the
completed job's `model_kind` before choosing which `EvaluationSummary`
view to render.

### Testing the Model Evaluation & Benchmarking Engine (frontend)

`apps/dashboard/src/features/ml-evaluation/` follows the same layering as
`ml-training/`: pure types/API client (Zod-validated, covered indirectly
through the page-level mocks below), components in isolation, then the
page composition root.

**Components.** `benchmark-filters-bar.test.tsx` covers every field
rendering, Compare being disabled until at least one of dataset version /
target column / an experiment is given (mirroring the backend's own
`no_benchmark_target` rule), typing a target column calling `onChange`,
clicking Compare calling `onSubmit` once something is given, and selecting
an experiment from the multi-select `Autocomplete` adding its id to
`experimentIds`. `benchmark-comparison-table.test.tsx` covers one row per
candidate with one column per metric, a placeholder cell (`—`) for a
metric present on only some candidates, `completed_at`-descending default
sort, metric-driven ranking (best-first for a higher-is-better metric,
ascending for a lower-is-better one, with a numbered Rank column appearing
only once a metric is chosen), the details callback firing with the
clicked row's own candidate (not a stale/wrong one — rows re-sort, so the
test clicks the first _rendered_ row and asserts against whichever
candidate that resolves to), every row's Experiment/Training Job link
`href`, and the Model Artifact link's presence/absence based on
`model_artifact_url`. `best-model-summary.test.tsx` covers one card per
metric and that the component renders nothing when there is nothing to
summarize (an empty `container`, not a stray empty wrapper).
`metric-comparison-chart.test.tsx` covers a labeled bar rendering only for
a candidate that recorded the given metric, and rendering nothing when
none did. `metric-selector.test.tsx` covers every given metric name plus a
"None" option appearing, and `onChange` being called with the metric name
or `null` in both directions. `dataset-summary-card.test.tsx` covers every
field rendering from the candidate, and an em dash placeholder for a
missing field rather than a crash. `candidate-detail-dialog.test.tsx`
covers rendering nothing when no candidate is given, the model type/
experiment name/deep links/Dataset Summary Card all appearing once one is,
and the artifact link's absence when none was recorded.
`benchmark-export-menu.test.tsx` covers both format options appearing in
the menu and a download actually triggering — `URL.createObjectURL`/
`URL.revokeObjectURL` stubbed via `Object.defineProperty` (the same pattern
this codebase's other download-triggering tests already use) and
`HTMLAnchorElement.prototype.click` spied on directly, since jsdom has no
real anchor-click-triggered download to observe. `benchmark-history-table.test.tsx`
covers one row per past run, an empty-history message, and the
Reopen/Delete callbacks each firing with the clicked row's own run summary.
`metric-catalog-panel.test.tsx` covers metrics grouping correctly into
Classification/Regression sections. `lib/benchmark-export.test.ts` covers
`buildBenchmarkCsv`/`buildBenchmarkJson` directly (header row, one data row
per candidate, the best-metric summary lines, a verbatim JSON round-trip),
the `BENCHMARK_EXPORTERS` registry having exactly the two registered
formats, and `benchmarkExportFileName`'s sanitization. `lib/model-kind.test.ts`
covers `toModelKind` passing through each of the three recognized values
and returning `undefined` for anything else (including `"unknown"`, the
value a candidate carries when its `model_type` is no longer registered).

**One assertion-ambiguity gotcha, worth naming:** `logistic_regression`
(the mocked model type) appears in both the best-model-summary card and
the comparison table row simultaneously once a benchmark result renders —
`ml-evaluation-page.test.tsx`'s benchmark-run test asserts with
`(await screen.findAllByText(...)).length).toBeGreaterThan(0)` rather than
the single-match `findByText`, the same fix this codebase's other
dual-rendering pages (e.g. `evaluation-summary.test.tsx`) already needed.
A second, unrelated ambiguity: `MetricCatalogPanel`'s "Classification
metrics"/"Regression metrics" headings render unconditionally (the group
title, not its row data, is static JSX) — a test awaiting the heading via
`findByText` resolves before the mocked `fetchMetricCatalog` promise
actually settles, so the metric-name assertion that follows must itself be
a `findByText` (awaiting the async data), not a synchronous `getByText`
chained after the heading.

**Page-level.** `ml-evaluation-page.test.tsx` covers: the empty-state
notice shown before any comparison has been run; the metric catalogue
rendering (grouped, from the mocked `fetchMetricCatalog`); a full benchmark
run (typing a target column, clicking Compare, asserting `runBenchmark` was
called with the expected body, then asserting the comparison table and
best-model-summary content appear); and an `empty_benchmark` rejection
rendering as an informational (not error-styled) message using the API
error's own `message` text directly, mirroring the backend's
`EmptyBenchmarkError` detail string rather than a re-derived one.

**The Machine Learning Training Framework's own page test gained one new
case for the reciprocal side of the deep link:** `ml-training-page.test.tsx`'s
"opens the detail dialog automatically for a `?jobId=` deep link" test sets
a mocked `next/navigation` `useSearchParams()` to return `{ jobId: 'job-1'
}` before rendering, and asserts the detail dialog's "Status Monitor"
appears with no click needed — `next/navigation` is mocked at the top of
that file the same way `history-page.test.tsx` already mocks it for its own
`useSearchParams` usage, with a module-level `searchParams` variable reset
to an empty `URLSearchParams` in `beforeEach` so every other existing test
in that file is unaffected.

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
