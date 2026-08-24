# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),

## [Unreleased]

### Added

- **Indicator Management & Chart Overlay System — production-readiness
  review** — a UX/scalability pass adding researcher-facing polish and one
  real caching improvement on top of the system below, with **zero
  breaking changes** to the batch endpoint, the store's existing actions,
  or any existing indicator.

  - **Category grouping**: the Indicator Panel's Available Indicators list
    is now grouped under `ListSubheader`s in a canonical order (Trend,
    Momentum, Volatility, Volume, Oscillators, Statistical, then any
    uncurated category) via a new, UI-only `groupIndicatorsByCategory` —
    the backend's `category` field remains a free-form string, so a future
    indicator's brand-new category still renders correctly with no schema
    change.
  - **Upgraded search**: `matchesIndicatorSearch` now matches name, label,
    category, every declared alias, and the description — not
    label/name/category alone. A new, additive `aliases: string[]` field
    was added to `IndicatorMetadata`/the catalogue API and populated for
    SMA, EMA, WMA, and RSI (e.g. `sma` → `["MA", "Moving Average", "Simple
MA"]`).
  - **Comprehensive per-indicator tooltips**: every entry in the Available
    Indicators list now carries an `InfoTooltip` with Purpose, Formula,
    Interpretation, Typical Parameters, Advantages, Limitations, and
    Common Use Cases — reusing the exact curated `IndicatorKnowledge` the
    standalone `/indicators` page's Information Panel already renders,
    via a new `toTooltipSections` helper, never a second copy of it.
  - **Manual color customization**: a new `OverlayColorSwatch` (shared by
    the panel and legend) turns the previously-static color dot into a
    picker — choose from a wider palette or reset to the automatic
    rotation — backed by a new, optional `OverlayConfig.colorOverride`
    field and a `setOverlayColor` store action. `resolveOverlayColor`
    resolves the override when present, the automatic rotation otherwise.
  - **Drag-and-drop + keyboard reordering**: the Indicator Legend's rows
    are now reorderable via native drag-and-drop or up/down icon buttons
    (kept for keyboard-only users), backed by a new `moveOverlayToIndex`
    store action. Render order — both the legend's list order and the
    chart's line paint order — follows this array's order directly:
    `CandlestickChart`'s Overlay Engine now detects a pure reorder (same
    overlay ids, new sequence) and recreates every series in the new
    order, since lightweight-charts paints series in creation order; an
    unrelated add/remove/toggle is unaffected and still only touches what
    actually changed.
  - **Improved loading/empty states**: the panel's catalogue loading state
    is now `Skeleton` rows instead of plain text, with a one-click "Clear
    search" on a no-match state; the legend's empty state adds an icon and
    points a researcher at the panel.
  - **Expanded calculation metadata**: the batch endpoint now reports
    Calculation Time, Cache Status, Dataset Size, Warmup Period, Engine
    Version, and Source Price — `IndicatorBatchResponse` gained
    `candles_analyzed`/`database_time_ms`/`engine_version`/`generated_at`
    (shared by the whole batch), `IndicatorBatchItemResult` gained
    `warmup_candles`/`execution_time_ms` (per item). A new
    `ENGINE_VERSION` constant versions the execution pipeline itself,
    independent of any indicator's own version. Surfaced per overlay via a
    "Details" `InfoTooltip` in both the panel and legend.
  - **Overlay-set export**: a new `OverlayExportMenu` offers CSV, JSON, and
    copy-to-clipboard for the _current_ overlay set (not just one
    indicator at a time), unioning overlays with different warmup lengths
    into one aligned table.
  - **Frontend-side result reuse**: a new `createOverlaySeriesCache` closes
    a redraw-layer gap — TanStack Query's structural sharing already kept
    an unchanged batch result's reference stable across refetches, but the
    existing `toOverlaySeries` rebuilt every overlay's data array on every
    call regardless, defeating the chart's own reference-equality
    redraw-skip. The new cache returns the same series object (and
    `data` array) for an overlay whose result reference and color are both
    unchanged, so "only modified indicators are recalculated" (engine
    layer) now also holds as "only modified overlays are redrawn" (chart
    layer). `toOverlaySeries` itself is unchanged and still independently
    tested.
  - 5 new backend tests (aliases, batch-level and per-item metadata) and
    over 60 new/updated frontend tests across the store, library, and
    component layers — full suites still pass (backend 558, frontend
    1094).
  - See `ARCHITECTURE.md` § "Indicator Management & Chart Overlay System —
    Production-Readiness Review", the updated `FRONTEND.md` § "Indicator
    Management & Chart Overlay System", and `docs/api/API.md` § "Technical
    indicators" for the full write-up.

- **Indicator Management & Chart Overlay System** — infrastructure for
  running several already-registered indicators as simultaneous chart
  overlays, built so the system scales to dozens of indicators without
  another chart-architecture change. Backend and frontend both purely
  additive; the full pre-existing backend and frontend suites pass
  unchanged.

  - **Batch calculation endpoint**: `POST
/api/v1/markets/{symbol}/indicators/batch` loads a market's candles
    **once** and runs up to 50 requested indicators against that single
    in-memory list, instead of one request per indicator each repeating the
    same candle query. Each requested indicator succeeds or fails
    independently — one bad indicator name or out-of-range parameter never
    blanks out every other correctly-configured overlay. `IndicatorService`
    gained a private `_load_points` helper shared by both the existing
    `calculate` and the new `calculate_batch`, with zero change to
    `calculate`'s external behavior.
  - **Overlay Engine**: `CandlestickChart` — the same primitive History,
    Live Market, and Replay already render — gained an optional
    `overlays` prop and a reconciliation effect that creates/removes
    `lightweight-charts` line series by overlay id and skips `setData()`
    entirely when an overlay's data reference is unchanged from the last
    push, avoiding unnecessary redraws (verified by a dedicated test).
  - **Indicator Panel** (`src/features/indicator-overlays/components/indicator-panel.tsx`):
    search, add, remove, enable/disable, and configure — with no
    indicator-specific code of its own, reusing the existing
    `useIndicatorCatalog` hook and `ParameterForm` component from the
    standalone `/indicators` page rather than duplicating either.
  - **Indicator Legend**: Name, resolved parameters, a visibility toggle,
    and a remove action per overlay, reading directly from the overlay
    store, independent of the panel.
  - **Session-scoped state**: a new Zustand store
    (`use-overlay-store.ts`) using the `persist` middleware against
    `sessionStorage` — the first persisted store in this codebase (the
    existing `ui-store.ts` is unpersisted) — chosen specifically because
    the requirement is "the current session," not indefinite persistence.
    Deliberately flat and plain-JSON-serializable so a future saved-
    workspace feature is a persistence-backend swap, not a redesign.
  - **Replay compatibility**: `ReplayChart` accepts the same `overlays`
    prop and reveals each overlay progressively by slicing to the current
    replay tick, mirroring the existing candle-reveal pattern exactly —
    verified with dedicated tests, and backward compatible by default
    (`overlays` defaults to `[]`).
  - Wired into `HistoryPage` today (panel, chart overlays, and legend all
    present); Replay and Live Market already accept the same `overlays`
    prop end-to-end but are not yet wired to the panel/store.
  - See `ARCHITECTURE.md` § "Indicator Management & Chart Overlay System",
    `FRONTEND.md` § "Indicator Management & Chart Overlay System", and
    `docs/api/API.md` § "Technical indicators" for the full write-up.

- Trend Indicator Package production-readiness review — a hardening pass
  over SMA/EMA/WMA before more indicator families are built on top of this
  engine, with **zero breaking API changes** and the existing architecture
  fully preserved.

  - **Shared Moving-Average Utilities** (`app/indicators/builtin/common.py`):
    SMA, EMA, and WMA had each independently declared an identical
    `period`/`source` parameter shape and an identical "warmup equals the
    period" rule — extracted into four small, optional helpers
    (`period_parameter`, `source_parameter`, `period_warmup`,
    `single_series_output`) all three (and RSI) now call, with no change to
    any indicator's external behavior.
  - **A real performance bug fixed**: WMA's `calculate` was O(n times period)
    — a fresh weighted re-sum per window — despite the engine's O(n) design
    intent. Replaced with a true O(n) incremental update, verified against an
    independent from-scratch reference computation to produce identical
    results.
  - **Numerical stability documented**: SMA/WMA's running-sum accumulation is
    stable indefinitely; EMA's recursive formula carries floating-point
    rounding forward by design (an accepted property of the formula, not a
    defect), verified to stay finite and in-range over a 5,000-candle series;
    no rounding is ever applied server-side.
  - **Metadata contract extended** with four additive fields — `version`
    (indicator-level semver), `author`, `complexity` (free-form Big-O), and
    `warmup_description` — deliberately not adding separate "output type" or
    "supported price sources" fields, since both are already derivable from
    `outputs`/`source.choices` and a parallel field would risk drifting out
    of sync.
  - **Parameter validation messages** now recommend the spec's own declared
    default on a bound violation (for example, a period of `0` against a
    minimum of `1` now also names the recommended default) — reusing the one
    number the spec already vouches for, never a fabricated suggestion;
    omitted for a required parameter, which has none.
  - **A design correction on the frontend**: the Results Summary's
    "Bullish"/"Bearish"/"Neutral" badge was, for a plain trend indicator,
    entirely synthesized from trend direction alone — manufacturing a
    trading signal out of a number that never carried one. The classifier
    (renamed from `classifySignal` to `classifyState`) now only returns a
    reading when the indicator itself defines a convention (RSI:
    "Overbought"/"Oversold"/"Neutral", still fully analytical, never an
    instruction to trade); SMA/EMA/WMA show Trend Direction only, with no
    fabricated state. Chart reference-line coloring moved from success/error
    (green/red — this codebase's "good/bad" colors) to neutral
    info/warning/divider tones.
  - The **Indicator Metadata card** now sources category, complexity,
    warmup description, version, and author from the backend's real
    per-indicator fields, replacing the previous hardcoded "O(n)" and "Not
    exposed by the API" placeholders — closing a gap the prior review had
    explicitly flagged as an honest limitation.
  - New **Current Price** and **Distance from Current Price** rows in the
    Results Summary, reusing the existing latest-candle endpoint (no
    indicator-response schema change) and comparing against the same price
    field the indicator's own `source` parameter resolved to.
  - **Exports** (CSV/JSON) now include the indicator's formula and purpose
    from the knowledge base when available, additive to every field the
    calculation response already carried.
  - 63 new/updated backend tests (large datasets for SMA/EMA, bit-for-bit
    determinism including through the result cache, an unsupported price
    source, complete engineering metadata, nullable optional candle fields,
    the new parameter-recommendation message) and frontend test updates
    across the result-analysis, result-summary, indicator-chart, and
    indicator-metadata-card suites, plus a new current-price test file —
    full suites still pass (backend 541, frontend 990).
  - See `ARCHITECTURE.md` § "Technical Indicator Engine" (new "Shared
    Moving-Average Utilities", "Numerical stability", "Complexity analysis",
    "Metadata contract", and "Future compatibility" subsections — EMA
    crossovers, a Moving Average Ribbon, MACD, Bollinger Bands, Hull MA,
    VWMA, and KAMA all verified to fit the existing contract with no engine
    change), `API.md`, and `TESTING.md`.

- Trend Indicator Package — Weighted Moving Average (`wma`), the third
  member of the `trend` category alongside the already-shipped SMA and
  EMA. Registered as an independent plugin
  (`services/api/app/indicators/builtin/wma.py`) with **zero changes to
  the engine, registry, API, or frontend** — the extensibility claim
  documented for the indicator engine foundation, now proven in practice
  rather than only asserted. WMA weights each candle in its window
  linearly by recency (oldest candle weight 1, newest weight N, divided
  by N(N+1)/2), sitting between SMA (equal weighting) and EMA (recursive,
  unbounded memory): it reacts faster than an SMA of the same period, but
  — unlike an EMA — an outlier ages out completely once it leaves the
  window rather than lingering in a recursive average. Parameter
  validation (`period` in `[1, 1000]`, `source` constrained to
  open/high/low/close) and error handling (`insufficient_data`,
  `invalid_indicator_parameter`) are entirely inherited from the shared
  engine pipeline; WMA declares its parameters the same way SMA/EMA do
  and needed no indicator-specific validation code. 12 new unit tests
  (`TestWeightedMovingAverage`) cover a hand-computed value, the warmup
  boundary, the source parameter, a faster-than-SMA reaction after a
  price jump, constant prices, an empty dataset, invalid periods (zero
  and negative), and a 5,000-candle dataset cross-checked at four points
  against an independent from-scratch weighted-average computation — not
  merely "it didn't crash." One new API integration test calculates WMA
  over real stored candles against a hand-computed expected value. The
  frontend's indicator knowledge base (`lib/indicator-knowledge.ts`)
  gained a curated `wma` entry (purpose, formula, advantages/limitations,
  recommended periods) with no other frontend change required — the
  already-generic parameter form, results summary, chart, and export
  utilities all picked it up automatically. See `ARCHITECTURE.md` §
  "Technical Indicator Engine" (now covering "The Trend Indicator
  Package"), `API.md`, and `TESTING.md`.
- Technical Indicators page usability review — transformed `/indicators`
  from a functional-but-plain form into a research interface, without
  touching the indicator engine, the backend, or the API contract.
  Every existing calculation and validation path is unchanged; this is
  additive UI/UX work plus a small amount of shared-infrastructure
  promotion. **Contextual tooltips** (ⓘ icon) beside every field —
  Market, Timeframe, Indicator, every parameter, Warmup Candles, Candles
  Analyzed, Calculation Time, Cache Status, Latest Value, and the Results
  Table — sourced from one dictionary per surface
  (`lib/field-help.ts` for fixed fields, `lib/indicator-knowledge.ts` for
  parameters) via a new shared `InfoTooltip`
  (`src/components/info-tooltip.tsx`), promoted out of the Trade Analytics
  dashboard's `MetricInfo` once this page needed the identical
  hover-and-keyboard-focus affordance; `MetricInfo` now delegates to it
  with no change to its own external behavior (its existing 5 tests pass
  unmodified). A new **Indicator Information Panel**
  (`IndicatorInfoPanel`, collapsible via a real `Accordion`) replaces the
  previous one-line description with category, purpose, mathematical
  intuition, a plain-text formula, recommended parameter values,
  advantages, limitations, typical use cases, common interpretation, and a
  methodology reference — curated for SMA/EMA/RSI in a new, purely
  additive knowledge base (`lib/indicator-knowledge.ts`) that degrades to
  an honest generic fallback (never a fabrication) for any indicator it
  hasn't curated, since the engine is explicitly designed to grow toward
  hundreds. **Parameter inputs** now show a curated tooltip and a row of
  recommended-value chips (e.g. RSI period: 7/9/14/21/25) that write
  straight to the field on click, falling back to just the backend's
  own description when a parameter has no curated entry. The **results
  summary** (`ResultSummary`) expands the previous single "latest value"
  tile per series into latest, previous, absolute and percentage change,
  trend direction, and a Bullish/Bearish/Neutral signal badge — using an
  indicator's own convention when the knowledge base defines one (RSI:
  above 70 reads bearish regardless of current direction) or a generic
  trend-based fallback otherwise, computed by a new pure, independently
  tested `summarizeSeries` (`lib/result-analysis.ts`). A new lightweight
  **visualization** (`IndicatorChart`) plots the computed series as an SVG
  line, or, for an oscillator like RSI, a bounded plot with 30/50/70
  reference lines — deliberately not a second charting engine: its
  domain/path math was promoted out of the Trade Analytics `Sparkline`
  into a new shared `src/lib/svg-line-path.ts`, and `Sparkline` itself was
  refactored to call it with no change to its external behavior (its
  existing tests, and the dashboard that uses it, pass unmodified). A new
  **Indicator Metadata** card reports category, output type, time
  complexity, warmup requirement, live cache status, and that Replay/
  Backtesting/AI-Feature-Engineering support is an architectural property
  of the engine's design rather than a per-indicator flag — and states
  plainly that no engine-version endpoint exists yet rather than
  inventing one. New **researcher export utilities** (`ExportMenu`):
  Export CSV/JSON (via a shared `downloadBlob`, promoted out of the
  History page's export buttons), Copy Values (tab-separated, newest
  first), and Copy API Request (the literal REST URL for the calculation
  on screen, assembled client-side with no request made). A new **Recent
  Calculations** panel persists the last 10 calculations to `localStorage`
  — recorded from the response's own echoed, fully-resolved parameters so
  a rerun reproduces exactly what ran — with one-click rerun that fires
  the calculation immediately while the visible form fields catch up.
  Accessibility: every tooltip opens on keyboard focus as well as hover
  with an explicit accessible name, the info panel is a native `Accordion`
  rather than a hand-rolled disclosure, the chart and summary carry
  `role="img"`/`role="status"` with descriptive labels, and every
  color-coded signal pairs its color with a text label. 168 tests in
  `src/features/indicators/`, all passing; the promoted shared modules
  (`InfoTooltip`, `svg-line-path`, `csv`, `download-file`) were verified
  against every consumer's original test suite, not just the new one. See
  `FRONTEND.md` § "Technical Indicators" (fully rewritten) and
  `TESTING.md` for the complete test breakdown.
- Technical Indicator Engine foundation — the platform's Quantitative
  Analysis groundwork. A registry-backed execution pipeline
  (`services/api/app/indicators/`) for reusable analytical components,
  designed so indicators can serve Research, Replay, Backtesting, Paper
  Trading, Feature Engineering, and AI models from one implementation.
  **Architecture over quantity**: only three reference indicators ship
  (SMA, EMA, RSI), chosen to cover the three distinct shapes the contract
  must support — a simple window, a recursive/stateful calculation, and a
  multi-stage bounded oscillator — so a fourth has a close precedent to
  copy. Adding an indicator requires **no change to the engine, registry,
  service, API, or frontend**: drop a module into
  `app/indicators/builtin/`, subclass `Indicator`, declare its metadata,
  and decorate with `@register`; `pkgutil` discovery does the rest, and a
  test registers a brand-new indicator to prove the claim rather than
  assert it. Nothing in `app/indicators/` imports SQLAlchemy, FastAPI, or
  Pydantic, which is what keeps the same implementations reusable outside
  the REST API. The pipeline (resolve → validate → warmup check → cache →
  calculate → verify alignment) catches two failures that would otherwise
  be silent: an under-sized range raises `insufficient_data` with the
  required and available counts rather than returning an all-`null`
  series, and every output series is verified to align index-for-index
  with the input candles — a misaligned series would still plot, just
  against the wrong timestamps. A bug inside one indicator is wrapped as
  `indicator_execution_failed` naming the culprit, never an anonymous 500.
  Three new endpoints: an indicator catalogue (publishing each parameter's
  type, bounds, choices, and default), a single-indicator description, and
  a per-market calculation whose indicator parameters are passed as
  ordinary query parameters, with unknown keys rejected rather than
  ignored. An optional bounded LRU result cache is included with its
  limits stated plainly — the key needs the candles, so a hit saves the
  recomputation but never the database read (measured: ~9.6 ms database
  vs ~0.08 ms compute for a 5-period SMA over 50 candles), and it is
  deliberately in-process rather than introducing the platform's first
  Redis dependency. New `/indicators` dashboard page
  (`apps/dashboard/src/features/indicators/`) with market, timeframe, and
  indicator selectors, a **parameter form generated entirely from the
  backend's published specs** (no per-indicator frontend code — the
  frontend half of the same extensibility guarantee), a results panel, and
  loading/error states. Also extracted the shared market-query validation
  (`app/services/market_query.py`) that the indicator and market-data
  services now both use, rather than a second copy of "is this timeframe
  supported"; `market_data.py` re-exports every moved error so existing
  imports are unchanged. See `ARCHITECTURE.md` § "Technical Indicator
  Engine", `API.md` § "Technical indicators", `FRONTEND.md` § "Technical
  Indicators", and `TESTING.md`.
- Historical Market Replay Engine (`/replay`,
  `apps/dashboard/src/features/replay/`) — configure a market, timeframe,
  and date range, load the whole session's candles once up front, then
  step or auto-play through them: Play/Pause/Resume/Stop/Restart/Next/
  Previous, six speed multipliers (0.25x–10x, changeable mid-session
  without restarting), and a seekable timeline (drag, jump ±20 candles, or
  seek by progress percentage). Reuses the existing candlestick chart
  module (`CandlestickChart`/`ChartLegend`) unmodified — a new
  `useReplayChartSync` hook translates replay position into that
  component's existing `candlesticks`/`liveCandle` props, so a session can
  auto-play through thousands of candles calling `series.update()` once
  per candle without ever calling `setData()` again after the initial
  seed, only reseeding on a genuine discontinuity (seek, previous,
  restart, stop). The replay state machine (`engine/replay-state-machine.ts`)
  and scheduler (`engine/replay-scheduler.ts`) are pure, framework-agnostic,
  and unit-tested with no React involved (47 and 9 tests respectively),
  matching this codebase's established "engine in a ref, hook as thin
  adapter" pattern. No backend change was needed: the existing
  `GET /markets/{symbol}/candles` endpoint already supports everything a
  replay session needs, loaded via `fetchAllCandles`
  (`apps/dashboard/src/lib/api/paginate-candles.ts`), promoted from a
  private helper in the History page's CSV/JSON export once Replay needed
  the identical "fetch every page of a query" behavior. Only OHLCV candles
  are replayed — `services/api/app/models/` persists no historical
  tick-level trade log or order-book snapshot store to replay instead;
  documented (currently unused) extension-point interfaces
  (`extension-points.ts`) exist for historical trades, historical order
  books, technical indicators, AI prediction playback, and paper trading,
  for whenever backend support for any of them exists. A stress test
  simulates a 24-hour, 1,440-candle session (and a 6-hour, 360-candle one
  driven through the scheduler) to verify per-tick cost stays flat rather
  than growing. See `FRONTEND.md` § "Historical Market Replay Engine" and
  `TESTING.md` § "Testing the Historical Market Replay Engine".
- Historical Market Replay Engine senior-level review pass: a new
  centralized `ReplayClock` (`engine/replay-clock.ts`, a small in-process
  publish/subscribe primitive mirroring the backend's own broker-free
  `EventBus`) is now the single source every replay-synchronized module
  reads its position from — `useReplayEngine` broadcasts one
  `ReplayClockTick` (phase, candle, timestamp, speed, discontinuity) after
  every dispatch, and `ReplayChart` reads it via a new
  `useSyncExternalStore`-backed hook, `useReplayClockTick`, instead of
  receiving `currentIndex`/`revealEpoch` as raw props — proving the
  synchronization guarantee is real today rather than only documented for
  later. `extension-points.ts`'s interfaces for future Trade Tape/Order
  Book/indicator/AI-prediction/paper-trading/backtesting modules now each
  carry a `clock: ReplayClock` field for the same reason. Adds a redesigned
  status panel (replay time, current/loaded/remaining candles, speed, and
  an estimated time to completion, built from the shared `StatTile`),
  timeline improvements (elapsed/remaining duration, jump-to-start/end,
  a live percentage shown while dragging the seek slider), full keyboard
  shortcuts (Space, ←/→, Home/End, +/-, via a new
  `useReplayKeyboardShortcuts` hook that skips typing targets and a
  focused slider), and a tooltip on every control naming its keyboard
  shortcut where one exists. Fixes a real state-machine gap found during
  this pass: seeking (or jumping to end) directly onto the last candle
  previously left replay `paused` with nothing left to advance to, rather
  than `completed`. Fixes a real, previously-missing `React.memo` on
  `ReplayConfigForm`, which had been re-rendering on every playback tick
  despite its own props never changing — caught and proven by a new
  render-cost test (`replay-page.render.test.tsx`) that spies on
  `useTimeframes` and fails immediately if the wrapper is removed. See
  `FRONTEND.md` § "Historical Market Replay Engine" (now covering "The
  Replay Clock" and "Keyboard shortcuts") and `TESTING.md` for the full
  test breakdown.
- Historical candlestick chart (TradingView lightweight-charts) as a
  reusable module (`apps/dashboard/src/components/chart/`), integrated as a
  new **Chart** tab on the History page alongside the existing candle
  table. Reuses the History explorer's existing market/timeframe/date-range
  filters and the existing `GET /markets/{symbol}/candles` endpoint (no
  new backend API); supports 10,000+ candles per render via transparent
  client-side pagination. See `FRONTEND.md` § "Chart module".
- Live Market Dashboard (`/live-market`) — real-time price card, live-
  updating candlestick chart, and trade tape for one symbol. Required the
  platform's first server-to-browser push channel: a new WebSocket gateway
  at `/api/v1/ws/market` (`services/api/app/marketdata/gateway.py` +
  `app/api/v1/endpoints/market_stream.py`) that relays trade/ticker events
  already flowing through the existing event bus — the frontend never
  connects to Delta Exchange directly. Reuses the chart module, its
  market/timeframe selectors in standalone mode, and the existing
  `/candles/stats` endpoint for 24h high/low/volume. See `FRONTEND.md` §
  "Live Market Dashboard" and `ARCHITECTURE.md` § "Backend".
- Live Order Book Viewer (`/orderbook`) — synchronized bid/ask depth
  tables with cumulative-depth bars, a spread summary (best bid/ask,
  spread, spread %, mid price), and a 10/25/50/100 depth selector for one
  symbol. Required a new backend component,
  `services/api/app/marketdata/orderbook.py`'s `OrderBookAggregator`,
  which reconstructs a coherent per-symbol L2 book from the event bus's
  snapshot + incremental-diff stream — `MarketStateManager` deliberately
  doesn't do this (its own docstring: "order book reconstruction ... is a
  consumer concern"), and naively relaying the raw stream would have
  wiped a multi-thousand-level book down to a single level roughly ten
  times a second (verified against the real exchange feed). The existing
  `/api/v1/ws/market` gateway was extended with a new `orderbook` message
  type rather than adding a second WebSocket endpoint. The frontend reuses
  the Live Market Dashboard's `useMarketStream` (extended with a
  `latestOrderBook` field), `MarketSelector`, `ConnectionStatus`, and
  market-candidate-ordering policy rather than duplicating any of them.
  See `FRONTEND.md` § "Live Order Book Viewer" and `ARCHITECTURE.md` §
  "Backend".
- Live Trade Analytics dashboard (`/trades`) — a live trade tape (with a
  new Trade Value column), session-wide buy/sell statistics (volumes,
  ratio, average trade size, largest trade by notional value, trade
  count), session and rolling 1m/5m/15m VWAP, and rolling-window analytics
  (trades/minute, volume/minute, average trade size, largest trade,
  buy/sell imbalance) for one symbol — no backend change required;
  everything is derived client-side from the existing `trade` messages the
  gateway already relays. Session statistics are O(1) running accumulators
  (`lib/session-stats.ts`), not a re-summed trade list, so they stay
  bounded in memory regardless of session length; rolling figures come
  from a single 15-minute time-pruned buffer. Neither can be derived from
  `useMarketStream`'s own display-capped trade array, which motivated a
  new `onTrade` option on that hook — called for every trade exactly once,
  before rAF batching or the tape's row cap apply. Reuses
  `useMarketStream` (trades-only via its `channels` option),
  `ConnectionStatus`, `MarketSelector`, and `TradeTape` (extended with an
  optional Trade Value column). `useOrderBookMarket`/`useOrderBookUrlState`
  were promoted and renamed to `useLiveTrackedMarket`/`useSymbolUrlState`
  once this page needed the exact same market-resolution behavior, rather
  than a third copy. A new shared `StatTile` component
  (`src/components/stat-tile.tsx`) replaces what would have been a third
  local reimplementation of the "label + big value" tile already
  duplicated between the Live Market price card and the Order Book spread
  panel. See `FRONTEND.md` § "Live Trade Analytics Dashboard".

### Changed

- Live Market Dashboard hardened for research use: it now resolves which
  market to show (URL → remembered → `ETHUSD` → live-tracked → any active)
  and validates each candidate for stored candles and live-feed support
  instead of defaulting to the alphabetically-first catalogue entry, which
  opened the page on `1000BONKUSD` with every panel empty; the selection is
  persisted to the URL and `localStorage`. Adds an operational connection
  panel (backend API, WebSocket, historical sync, market state, last
  message, reconnect attempts, heartbeat latency), informative empty states
  explaining _why_ data is missing with a retry, `Unavailable` in place of
  placeholder dashes, last-trade/last-candle times on the price card, and
  buy/sell colouring in the trade tape. Live updates are now batched
  (~10 commits/second) and the forming candle is seeded from the last
  historical bar, so history loads first and the live bar continues it.
  See `FRONTEND.md` § "Live Market Dashboard".
- Live Trade Analytics dashboard reworked into a quantitative research
  workstation. **Information hierarchy**: a new dominant `PriceHeader` band
  (current price coloured by aggressor side, session high/low, distance
  from VWAP, live trades-per-second with an activity pulse) sits above four
  labelled `Section` landmarks — Order Flow, VWAP, Session Statistics,
  Connection — replacing a flat run of same-weight panels separated by
  rules; panels no longer render their own `Paper`, so borders are not
  nested inside borders. **Contextual help**: every metric now carries a
  keyboard-reachable Info button whose tooltip explains what it is, why it
  matters, how it is calculated, and how to read it, all sourced from one
  dictionary (`lib/metric-help.ts`) so the same metric cannot be explained
  two different ways in two panels. **New analytics**: distance from VWAP,
  session high/low, trades-per-second (measured over ten seconds, not a
  scaled-down minute), and a trade size distribution bucketed relative to
  the window's own average so it reads identically on a $2 asset and a
  $70,000 one. **Trade tape**: zebra striping, a sticky timestamp column,
  memoized rows, CSV export of the visible rows with the active filters
  recorded in the file, a "showing N of M rows" readout so a filtered tape
  is never mistaken for a quiet market, and opt-in virtualization above 60
  rows (spacers `aria-hidden`, `aria-rowcount` still correct).
  **Performance**: a new render-cost suite
  (`trade-tape.render.test.tsx`) asserts how many rows actually re-render,
  by spying on a formatter each row calls a fixed number of times. It
  immediately caught a real bug that reads as obviously correct in source —
  zebra-striping rows by array index flipped every row's props whenever a
  trade was prepended, forcing 101 row renders per trade; striping by the
  stable per-trade key instead brought that to 1. **Accessibility**:
  `region` landmarks per section, `scope="col"` headers, `role="meter"`
  gauges with `aria-valuetext` giving both a percentage and a raw count,
  decorative elements `aria-hidden`, and colour never used as the only
  channel. No backend change; still no AI, model, or trading signal
  anywhere on the page. See `FRONTEND.md` § "Live Trade Analytics
  Dashboard" and `TESTING.md` § "Asserting render cost, not just render
  output".
- Live Trade Analytics dashboard quant-UI and performance pass: every
  calculation now lives behind a dedicated `TradeAnalyticsEngine`
  (`src/features/trades/engine/trade-analytics-engine.ts`) so
  `useTradeAnalytics` and every component only consume an already-computed
  snapshot; the rolling trade window moved from an array copied on every
  insert to a capacity-bounded `RingBuffer` (O(1) push, no per-trade copy),
  with every window calculation now filtering by timestamp at read time via
  binary search rather than assuming pre-pruned input. Adds sparkline trends
  (Buy vs Sell Volume, Trades/Minute, Volume/Minute, Rolling VWAP, Average
  Trade Size) from a new, separately-sampled metric-history ring buffer; a
  Market Sentiment summary and Buy/Sell pressure gauge derived from the
  existing rolling imbalance figure (a fixed threshold table, not a
  prediction); dedicated session and last-minute Largest Trade cards
  showing Time/Side/Price/Quantity/Value explicitly, replacing a
  value-plus-caption stat tile; and trade tape enhancements — an
  incoming-row animation and an unusually-large-trade highlight (both
  enabled by fixing the tape's row keys to a stable per-trade identity
  instead of an array index that shifted on every new trade, which had
  been causing the entire table body to remount on every trade), plus
  Buy/Sell/All and minimum-trade-size display filters that never touch the
  underlying accumulators. A stress test simulates a ~30-minute sustained
  session to verify calculation cost stays flat with session length — see
  `FRONTEND.md` § "Live Trade Analytics Dashboard" and `TESTING.md` for the
  disclosed limits of that verification (no browser automation is
  available to measure real heap/paint behavior over 30 actual minutes).
- Order Book viewer performance pass: `useMarketStream` (shared with the
  Live Market Dashboard) now batches via `requestAnimationFrame` instead
  of a fixed 100ms timer, and gained a `channels` option so a consumer
  can opt out of message types it doesn't use — the Order Book page
  disables `trades`/`ticker` entirely, since it was previously re-rendering
  on every trade tick despite never reading trade data. Each order book
  row is now its own `React.memo`-wrapped component with a value-based
  comparator (`orderBookRowPropsAreEqual`), so a row whose price/size/
  total/depth-ratio are unchanged skips re-rendering even though its
  parent table re-rendered. See `FRONTEND.md` § "Live Order Book Viewer →
  Performance considerations" for the full before/after reasoning and the
  known scalability limits.

### Deprecated

### Removed

### Fixed

- **Critical**: the Live Market Dashboard never displayed any live data —
  current price, trade tape, and last-trade time stayed "Unavailable"
  indefinitely even on a healthy, connected stream. Root cause: the
  WebSocket gateway serialized `event_time` with `datetime.isoformat()`,
  which renders a `+00:00` offset for a UTC-aware datetime; the frontend's
  `z.string().datetime()` schemas accept only a literal `Z` suffix by
  default, so every single trade/ticker/snapshot frame failed validation
  and was silently dropped. Heartbeat pongs carry no timestamp, so the
  connection still showed "Connected" with measured latency, masking the
  failure completely. Fixed by matching the REST layer's own `Z`-suffix
  convention (`app/schemas/market_data.py`) in the gateway's payload
  builders (`app/marketdata/gateway.py`'s new `_isoformat_utc`). Regression
  tests pin the wire format on both sides: backend
  (`test_gateway.py::TestWireTimestampFormat`) and frontend
  (`src/types/api/market-stream.test.ts`).
- Added debug-level structured logging at the three pipeline stages that
  previously had none — normalize-and-publish (`app/marketdata/pipeline.py`),
  market-state update (`app/state/manager.py`'s `_touch`), and gateway
  fan-out (`app/marketdata/gateway.py`'s `_enqueue`) — so `APP_LOG_LEVEL=DEBUG`
  now traces a message through every stage: WebSocket receive → parse →
  event bus → state update → gateway send. The event bus and Delta client
  already logged their stages; only these three were silent.
- Trade `side` is now normalized from Delta's compact `trades` channel
  instead of being hard-coded to `"unknown"`. The channel's `r` field
  carries the buyer's role, which the normalizer was discarding; verified
  against the exchange by cross-checking 55 fills against the verbose
  `all_trades` channel's `buyer_role`/`seller_role` (`r="t"` ⇔ aggressive
  buy, `r="m"` ⇔ aggressive sell, no counterexamples). The Live Market
  trade tape colours rows by this real side rather than by price direction.
- The Live Market chart no longer risks a lightweight-charts exception when
  a historical refetch lands while a forming bar for an earlier bucket is
  on screen; out-of-order `series.update()` calls are dropped.
- `history-page.test.tsx`'s preset-range assertion compared its captured
  timestamp against a later `now` in the wrong direction, so it failed
  whenever the two landed in different seconds.

### Security

## Versioning
