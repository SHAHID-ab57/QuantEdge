# System Architecture

## Document Information

> To be completed in future tasks.

## Purpose

> To be completed in future tasks.

## Architectural Principles

> To be completed in future tasks.

## System Context

> To be completed in future tasks.

## High-Level Architecture

> To be completed in future tasks.

## Core Systems

### Frontend

The frontend is a Next.js 15 / React 19 / TypeScript dashboard in
`apps/dashboard`, styled with a dark-only Material UI v7 theme and backed by
TanStack Query (server state) and Zustand (local UI state). See
[`FRONTEND.md`](FRONTEND.md) for the full breakdown of routes, the
feature-module pattern, the API client, and the reusable candlestick chart
module (`src/components/chart/`) that renders historical OHLCV data with
TradingView's lightweight-charts, and the Live Market Dashboard
(`src/features/live-market/`) that renders real-time price/chart/trade-tape
data over that gateway, resolving which market to show against the set the
backend actually streams rather than assuming any catalogue entry has data,
the Order Book viewer (`src/features/order-book/`) that renders live
depth tables and a spread summary over the same gateway's reconstructed
order-book messages, and the Live Trade Analytics dashboard
(`src/features/trades/`) that derives a live trade tape, session/rolling
statistics, VWAP and distance from it, sparkline trends, a trade size
distribution, and a market-sentiment summary from the same gateway's trade
messages — no backend change was needed for it; everything is computed
client-side from data the gateway already relays, behind a dedicated
`TradeAnalyticsEngine`
(`src/features/trades/engine/trade-analytics-engine.ts`) that owns every
accumulator (a capacity-bounded ring buffer for the rolling trade window,
an O(1) session accumulator, a small sampled history for sparklines) so
components only ever consume an already-computed snapshot, and the
Historical Market Replay Engine (`src/features/replay/`) that loads a
configured market/timeframe/date-range session's candles once up front and
steps or auto-plays through them, reusing the same candlestick chart
module rather than a second chart implementation. Its own
`ReplayScheduler`/`replayReducer`/`ReplayClock` (`src/features/replay/engine/`)
are pure, framework-agnostic, and unit-tested independent of React — the
clock, added in a later review, is a small in-process publish/subscribe
primitive (mirroring the backend's own broker-free `EventBus`) that
broadcasts one synchronized "current candle/timestamp/phase/speed" tick so
the chart, and any future replay-synchronized module, read the identical
position rather than each deriving it separately. No backend change was
needed for any of this; only OHLCV candles are replayed, since
`services/api/app/models/` persists no historical tick-level trade log or
order-book snapshot store to replay instead (documented extension points
exist for both, in `src/features/replay/extension-points.ts`, for whenever
that becomes a real backend feature). It talks to
`services/api` over the read-only REST surface described
in [`docs/api/API.md`](docs/api/API.md) for historical data, and over a
single WebSocket gateway (below) for live data — never directly to Delta
Exchange.

### Backend

`services/api` is a FastAPI service (async SQLAlchemy + PostgreSQL) — see
[`services/api/README.md`](services/api/README.md) for its own detailed
architecture. Two API surfaces exist:

- **REST** (`app/api/v1/endpoints/`): read-only market data and platform
  health/status/metrics, documented in
  [`docs/api/API.md`](docs/api/API.md).
- **WebSocket gateway** (`app/api/v1/endpoints/market_stream.py`, backed by
  `app/marketdata/gateway.py`'s `MarketStreamGateway`): the platform's
  first server-to-browser push channel, added for the Live Market
  Dashboard. It relays `TradeEventReceived`/`TickerUpdated` events already
  flowing through the in-process event bus (published by the Delta
  WebSocket client + processing pipeline — see `app/runtime.py`) to
  browser clients subscribed to a symbol, plus a reconstructed order-book
  view for the Order Book viewer (below). It does not add a new data
  source; it exposes data the runtime already collects.
- **Order book reconstruction** (`app/marketdata/orderbook.py`'s
  `OrderBookAggregator`): `MarketStateManager` deliberately does not
  reconstruct a coherent order book from Delta's snapshot + incremental-diff
  stream (its own docstring: "order book reconstruction ... is a consumer
  concern") — this component is that consumer. It subscribes to the same
  `OrderBookUpdated` bus event, replaces the book on a snapshot, and merges
  diffs (upsert non-zero sizes, drop zero-size levels) on an update, so the
  gateway always has a coherent, correctly-sorted book to relay rather than
  a single raw diff of a handful of changed price levels.

Both surfaces are served by the same `Runtime` composition root
(`app/runtime.py`), which now always constructs an `EventBus`, a
`MarketStateManager`, and a `MarketStreamGateway` — the gateway simply has
nothing to relay until live mode (`MARKET_DATA_LIVE=true`) starts
publishing events.

Only the symbols in `DELTA_MARKET_SYMBOLS` (default `BTCUSD,ETHUSD`) are
streamed or candle-synced; the `/markets` catalogue lists every Delta
product regardless. That asymmetry is a load-bearing architectural fact for
clients, not an implementation detail — a UI that picks a market from the
catalogue without checking it against the tracked set will render an empty
view. `/system/metrics`'s `state_latest_prices` is the authoritative list of
what is actually live, and the Live Market Dashboard resolves its market
against it (see [`FRONTEND.md`](FRONTEND.md) § "Market selection,
validation and fallback").

### Technical Indicator Engine

`services/api/app/indicators/` is the platform's Quantitative Analysis
foundation: a registry-backed execution pipeline for reusable analytical
components. Indicators are **not** an end goal here — they are the shared
building block that Research, Replay, Backtesting, Paper Trading, Feature
Engineering, and AI models are all intended to consume, so the design
optimises for adding hundreds of them cheaply rather than for shipping many
today.

**Layering.** The one rule everything else follows: nothing in
`app/indicators/` imports SQLAlchemy, FastAPI, or Pydantic, and no
indicator implementation may either. An indicator receives plain
`OHLCVPoint` values and returns plain series. That is what lets the same
implementation serve the REST API today and, unchanged, a replay session or
a backtest that gets its candles from somewhere else entirely.

```text
app/indicators/
├── base.py       Indicator ABC, OHLCVPoint, IndicatorContext/Output, metadata
├── params.py     ParameterSpec + coercion/validation
├── registry.py   IndicatorRegistry (+ the app-wide default_registry)
├── engine.py     IndicatorEngine — the execution pipeline
├── cache.py      Bounded LRU result cache
├── errors.py     Domain errors (all AppError subclasses)
└── builtin/      Auto-discovered indicator modules
    ├── common.py   Shared parameter/warmup/output helpers (see below)
    ├── sma.py, ema.py, wma.py   The Trend Indicator Package
    └── rsi.py      Momentum
```

`app/services/indicators.py` is the _only_ place the two halves meet: it
loads candles through the existing `CandleRepository`, projects them onto
`OHLCVPoint`, and hands them to the engine. Routers never touch SQL and
the engine never touches the ORM — both existing platform conventions hold.

**Registry pattern (Strategy + Registry).** The engine never imports a
concrete indicator; it asks the registry for one by name. Registration is
by decorator at class-definition time, and `app/indicators/builtin/`
imports every module in itself via `pkgutil` on startup. The practical
consequence is the guarantee the whole design exists for:

> **Adding an indicator requires no change to the engine, registry,
> service, API, or frontend.**

**Adding a new indicator** — the complete workflow:

1. Create `app/indicators/builtin/<name>.py`.
2. Subclass `Indicator`, declare a class-level `metadata:
IndicatorMetadata` (name, label, description, category, `ParameterSpec`s,
   `SeriesSpec`s — plus `version`/`author`/`complexity`/
   `warmup_description`, see "Metadata contract" below), and implement
   `calculate`. If it declares the common `period`/`source` shape, reach
   for `common.period_parameter`/`common.source_parameter` instead of
   writing the `ParameterSpec`s by hand — see "Shared Moving-Average
   Utilities" below.
3. Decorate the class with `@register`.
4. Override `warmup(params)` if the indicator needs N candles before its
   first value (`common.period_warmup` covers the "equal to the period"
   case).

That is the entire list. It appears in `GET /api/v1/indicators`
immediately, and the dashboard's `/indicators` page renders a correct,
constrained parameter form for it with no frontend work — because the form
is generated from the published specs. A curated research entry in
`apps/dashboard/src/features/indicators/lib/indicator-knowledge.ts` is
optional but recommended (formula, advantages/limitations, recommended
parameter values, chart configuration) — an indicator with none still
renders a complete, honest page via the knowledge base's generic fallback,
it just won't have the richer research content until someone adds it.

Three reference indicators shipped with the foundation, chosen to cover
the three distinct shapes the contract must support so a fourth has a
close precedent to copy: **SMA** (simple window), **EMA**
(recursive/stateful with a defined seed), and **RSI** (multi-stage,
bounded, warmup one longer than its period).

**The Trend Indicator Package** (`sma`, `ema`, `wma` — all `category:
"trend"`) is the first real test of that extensibility claim: **WMA**
(`app/indicators/builtin/wma.py`) was added afterward by following the
four-step workflow above verbatim, with zero changes to the engine,
registry, API, or frontend. WMA computes a linearly-weighted mean over the
window — the oldest candle in a period-N window carries weight 1, the
newest carries weight N:

```text
WMA(t) = (1·P(t-N+1) + 2·P(t-N+2) + ... + N·P(t)) / (1+2+...+N)
```

It sits between SMA (equal weighting) and EMA (recursive, unbounded
memory) on the recency-weighting spectrum: like EMA it reacts faster than
an SMA of the same period, but like SMA it is recomputed fresh over each
window rather than carrying state forward — so an outlier ages out
completely once it leaves the window, which an EMA's recursive formula
never fully does. Parameter validation (`period` bounded `[1, 1000]`,
`source` constrained to `open`/`high`/`low`/`close`) and error handling
(an under-sized range raising `insufficient_data`, an out-of-range
parameter raising `invalid_indicator_parameter`) are entirely inherited
from the shared engine pipeline — WMA declares its `ParameterSpec`s the
same way SMA/EMA do and gets the same guarantees for free, with no
indicator-specific validation code.

**Shared Moving-Average Utilities** (`app/indicators/builtin/common.py`).
A production-readiness review of the Trend Indicator Package found SMA,
EMA, and WMA had each independently declared an identical `period`
parameter shape, an identical `source` parameter shape, an identical
"warmup equals the period" rule, and an identical "wrap one series as the
output" line — three copies of code that would only grow with every
additional moving-average variant. `common.py` extracts four small,
optional helpers (`period_parameter`, `source_parameter`, `period_warmup`,
`single_series_output`) that all three now call; nothing about their
external behavior changed; RSI adopted `period_parameter`/`source_parameter`
too (declaring its own `minimum=2` override and its own `warmup()`, since
its warmup is the period _plus one_, not the common case). These are
conveniences, not a mandatory second base class — an indicator whose shape
doesn't fit (a future MACD taking two periods, an oscillator with a
different warmup rule) simply doesn't call them.

**Numerical stability.** Every indicator in this package is a pure
function of its input candles: same candles and parameters in, identical
`float` output every time — pinned explicitly by
`TestRepeatedCalculationIsDeterministic` (which also runs a calculation
once "live" and once served from the result cache, and checks the two
outputs are identical, not merely presumed to be). Two distinct stability
stories exist:

- **SMA and WMA** carry a running total (a plain sum for SMA, a plain sum
  plus a weighted sum for WMA) that only ever adds and removes values
  already present in the series. No repeated re-summation of a whole
  window means no compounding of rounding error beyond the one
  unavoidable float operation per step — the same behavior a from-scratch
  `sum()` at every point would have, just computed in O(1) instead of
  O(period) per point.
- **EMA** is the one genuinely recursive calculation: each point is
  derived from the _previous computed point_, not re-derived from the
  source data, so floating-point rounding at any step is carried forward
  into every subsequent value (attenuated by the smoothing multiplier
  each step, never fully purged). This is an accepted, well-documented
  property of the EMA formula itself, not a defect in this implementation
  — IEEE-754 double precision keeps the drift far below the six
  significant digits this platform ever displays, verified over a
  5,000-point series in `test_ema_stays_finite_and_bounded_at_scale`.

No rounding is applied anywhere on the backend — every value is the raw
`float` the calculation produced, serialized as a JSON number. Rounding is
strictly a frontend display concern (`Intl.NumberFormat` with six
significant digits), never fed back into a further calculation or
persisted; this keeps "what the engine computed" and "what a UI chose to
show" from ever silently diverging.

**Complexity analysis.** SMA, EMA, WMA, and RSI are all O(n) in the number
of candles analyzed — each declares this in its own `complexity` metadata
field (see "Metadata contract" below) rather than it being assumed. WMA is
the interesting case: a naive per-window re-sum is O(n · period), and an
earlier version of this indicator was exactly that, correct but
needlessly quadratic in the period. The production-readiness review
replaced it with an O(1)-per-point incremental update, using the identity

```text
weighted(t+1) = weighted(t) + N · x(t+1) - total(t)
total(t+1)    = total(t) - x(t+1-N) + x(t+1)
```

(`total` being the same plain running sum SMA already tracks), turning the
per-point cost from O(period) into O(1) after one O(period) seed for the
first window — the same complexity class as SMA and EMA. The optimization
is verified never to have changed the answer:
`test_matches_an_independent_reference_implementation_on_a_large_dataset`
cross-checks it at several points in a 5,000-candle series against a
from-scratch weighted-average computation written independently of the
production code.

**Metadata contract.** `IndicatorMetadata` (and its wire counterpart,
`IndicatorDTO`) carries four additive fields beyond the original
name/label/description/category/parameters/outputs contract:

| Field                | Meaning                                                                                                                                                                                                |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `version`            | Indicator-level semver, independent of the platform's release version — bump it when a change to `calculate` would alter previously-computed historical results.                                       |
| `author`             | Who owns this implementation.                                                                                                                                                                          |
| `complexity`         | A free-form Big-O / performance note, stated by the indicator itself rather than assumed by any consumer.                                                                                              |
| `warmup_description` | How the warmup candle count relates to this indicator's own parameters (e.g. "Equal to the period parameter"), distinct from the exact number a specific calculation reports in `meta.warmup_candles`. |

Deliberately **not** part of this contract: "Output Type" and "Supported
Price Sources" are not separate fields, because they are already fully
derivable from `outputs` and from the `source` parameter's `choices` —
adding parallel fields for them would risk drifting out of sync with the
data that already states them. The frontend's `IndicatorMetadataCard`
derives both rather than duplicating them. `complexity` and
`warmup_description` default to honest, neutral placeholders
(`"Not documented"` and an empty string respectively) rather than a
guessed value, so a future indicator that forgets to set them fails safely
instead of silently claiming a complexity it hasn't earned; `version`
(`"1.0.0"`) and `author` (`"Eth AI Platform"`) default to a sane starting
baseline for a first-party indicator, meant to be overridden by anything
built outside the core team.

**Execution pipeline.** One fixed sequence applied identically to every
indicator, with no branch on which indicator is running:

```text
resolve → validate parameters → check warmup → cache lookup
        → calculate → verify alignment → cache store
```

Two stages are worth calling out because they exist to catch failures that
would otherwise be silent:

- **Warmup check** — an under-sized range raises `insufficient_data` with
  the required and available counts, rather than returning a series that is
  entirely `null`. A chart of nothing looks identical whether the market
  was quiet or the range was too short.
- **Alignment verification** — every returned series must have exactly one
  value per input candle. A misaligned series would still serialize and
  still plot, just against the wrong timestamps; checking it centrally
  means every indicator gets the guarantee for free.

A bug inside one indicator is wrapped as `indicator_execution_failed` and
**names the culprit**, so one bad implementation never surfaces as an
anonymous 500 for the whole API.

**Caching.** An optional bounded LRU (`cache.py`), keyed by indicator,
parameters, and an O(1) fingerprint of the candle range. Its limits are
worth stating plainly: the key requires the candles, which the caller can
only have _after_ reading them, so a hit saves the recomputation and never
the database query. Measured against the live dev database, a 5-period SMA
over 50 candles spends ~9.6 ms in the database and ~0.08 ms computing — the
cache is close to irrelevant there, and earns its place only for
genuinely expensive indicators and repeated identical requests. It is
deliberately in-process rather than Redis-backed: `redis` remains a
declared-but-unwired dependency, and introducing the platform's first Redis
dependency for a cache that cannot avoid the dominant cost would be the
wrong trade. `IndicatorCache` is the seam if that changes.

**Parameter validation messages recommend the declared default.** A bound
violation (`app/indicators/params.py`'s `_check_bounds`) now appends
`(recommended: N)` to its error message, where `N` is the parameter's own
declared `default` — the one value the spec itself already vouches for as
sane. This is deliberately not a separate "recommended value" concept
layered on top: it reuses the single number every parameter already
carries, so there is nothing to keep in sync. A required parameter (no
default) gets no recommendation, since none exists to offer.

**The frontend displays analytical information, never a trading signal.**
A production-readiness review found the Results Summary's original
"Bullish/Bearish/Neutral" badge was, for a plain trend indicator, entirely
synthesized from trend direction alone — "the average is rising" was being
relabeled as "Bullish," which is manufacturing a signal out of a number
that doesn't carry one. Two changes fixed this:

- `IndicatorKnowledge.classifyState` (renamed from `classifySignal`)
  returns a descriptive `{ label, tone }` — for RSI, `"Overbought"` /
  `"Oversold"` / `"Neutral"`, describing where the oscillator sits
  relative to its own conventional thresholds — never a generic
  bullish/bearish reading synthesized from trend direction. An indicator
  with no established convention (every current trend indicator: SMA,
  EMA, WMA) has no `classifyState` at all, and `summarizeSeries` no
  longer fabricates one; `Trend Direction` (up/down/flat) is still
  reported on its own, since direction is a fact about the series, not a
  reading of market state.
- Reference-line coloring on the chart (RSI's 30/50/70 bands) moved from
  success/error (green/red — this codebase's "good/bad" colors, which
  would read as a buy/sell cue) to neutral `info`/`warning`/`divider`
  tones describing band _position_, not a verdict.

See `FRONTEND.md` § "Technical Indicators" for the full before/after.

**Future compatibility** — verified, not yet built. The engine's contract
(a `calculate(ctx) -> IndicatorOutput` returning one or more aligned
series, arbitrary `ParameterSpec`s, no dependency beyond `OHLCVPoint`) was
checked against every indicator family this package is expected to grow
into next, confirming none require an engine change:

| Future indicator                        | Why it fits today's contract                                                                                                                                                                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| EMA crossovers                          | Two already-independent EMA calculations compared client-side, or a new indicator taking two `period` parameters and returning both EMAs plus a crossover marker as extra series — `IndicatorOutput.series` is already an arbitrary-length list. |
| Moving Average Ribbon                   | N `period` values (a `string`/`float` list isn't supported today, but N _named_ periods, e.g. `period_1`..`period_5`, are) each producing one series — same multi-series contract.                                                               |
| MACD                                    | Three series (MACD line, signal line, histogram) from one `calculate` call — exactly the shape `IndicatorChart` already renders for any multi-series `IndicatorOutput`.                                                                          |
| Bollinger Bands                         | Three series (upper/middle/lower) plus a `float` `stddev` parameter — `ParameterSpec(type="float")` already exists.                                                                                                                              |
| Hull MA, VWMA, KAMA, other adaptive MAs | Each is a new `Indicator` subclass with its own internal state confined to one `calculate` call; VWMA additionally reads `candle.volume`, already present on every `OHLCVPoint`.                                                                 |

Nothing in this list needs a new engine stage, a new registry mechanism,
a new API shape, or a new frontend component — each is "write
`app/indicators/builtin/<name>.py`, register it" exactly as WMA was, which
is the whole point of the architecture this review was checking.

### Indicator Management & Chart Overlay System

Infrastructure, not a new indicator algorithm: a way to manage _several_
already-existing indicators as simultaneous overlays on one chart, built so
the system scales to dozens of indicators without another chart-architecture
change. It adds one backend endpoint and one new frontend feature module;
nothing about the engine, the registry, or any existing indicator changed.

**Backend: one batch endpoint, additive only.**
`POST /markets/{symbol}/indicators/batch` (`app/api/v1/endpoints/indicators.py`,
mounted at both `/api/v1/*` and unversioned per the existing convention)
accepts up to 50 `{indicator, params}` requests plus one shared
`timeframe`/`start`/`end`/`limit`, and returns one shared `timestamps` array
alongside a `results` list. `IndicatorService.calculate_batch`
(`app/services/indicators.py`) is why this is worth having: the market
lookup, timeframe/range/limit validation, and the single candle query — all
previously inlined in `calculate` — were extracted into a private
`_load_points` helper that both `calculate` and `calculate_batch` now share.
`calculate_batch` loads candles **once** and runs every requested indicator
against that one in-memory list, instead of the caller (or a naive frontend)
issuing N independent requests that would each repeat the same candle query.

Each item in the batch succeeds or fails **independently**:
`IndicatorNotFoundError`, `InvalidIndicatorParameterError`,
`InsufficientDataError`, and `IndicatorExecutionError` are caught per item
and packaged as `{success: false, error_code, error_detail}` rather than
failing the whole batch — one mistyped indicator name or one out-of-range
parameter must never blank out every other overlay a researcher already has
configured correctly. A failure that means there is no candle data to
compute anything from at all (unknown market, invalid timeframe/range/limit)
still raises normally and fails the whole batch, since no per-item result
would be meaningful. This is purely additive: `calculate` and the existing
single-indicator endpoints are untouched, and the full pre-existing backend
test suite passes unchanged.

**Frontend: `src/features/indicator-overlays/`.** Three concerns, each
reusing something that already existed rather than duplicating it:

- **Overlay Engine** (`src/components/chart/candlestick-chart.tsx`) — the
  reused `CandlestickChart` primitive (same component History, Live Market,
  and Replay already render) gained one new optional prop,
  `overlays?: OverlaySeriesInput[]`, and one reconciliation `useEffect`
  keyed on that prop. It tracks live `lightweight-charts` series in a
  `Map<string, ISeriesApi<'Line'>>` and each series' last-pushed data in a
  parallel `Map<string, LineData[]>`, both keyed by overlay `id`:
  - an id present in `overlays` but not yet in the map gets
    `chart.addSeries(LineSeries, ...)`;
  - an id in the map but no longer in `overlays` gets `chart.removeSeries()`
    and is dropped from both maps;
  - an existing series only calls `series.setData()` when its `data` array
    **reference** differs from the one last pushed — this is the "avoid
    unnecessary redraws" requirement, verified by a dedicated test
    (`does not re-push an overlay whose data reference is unchanged`) rather
    than merely asserted. Color/label changes go through `applyOptions()`,
    never a series recreation.
  - No chart, router, or lifecycle logic was added or changed — the Overlay
    Engine is additive to the same imperative "one effect per concern, refs
    hold instances" pattern this component already used for candles/volume.

- **Indicator Panel** (`components/indicator-panel.tsx`) — search, add,
  remove, enable/disable, and configure, with **zero indicator-specific code
  of its own**: it reuses `useIndicatorCatalog` (no duplicate catalogue
  fetch) and `ParameterForm` (no duplicate parameter-form implementation)
  from the standalone `/indicators` research page's feature module. A
  parameter edit is validated locally (`validateValues`, the same function
  `/indicators` already uses) and only committed to the store — and
  therefore only sent to the chart — once the whole draft is valid, so the
  chart keeps showing the last good configuration mid-edit instead of
  flashing an error state on every keystroke.

- **Indicator Legend** (`components/indicator-legend.tsx`) — Name,
  resolved parameters, a visibility toggle, and a remove action per overlay,
  reading directly from the overlay store; deliberately independent of the
  panel (either surface's remove/toggle action is sufficient on its own) so
  a legend can later be reused anywhere an overlay list needs to be shown
  without the full management panel.

**State management: `useOverlayStore` (Zustand + `sessionStorage`).**
`src/features/indicator-overlays/store/use-overlay-store.ts` is a new
Zustand store using the `persist` middleware with
`createJSONStorage(() => sessionStorage)` — the first persisted store in
this codebase; the existing `ui-store.ts` is Zustand but holds only
ephemeral, unpersisted sidebar state. `sessionStorage` (not `localStorage`)
was a deliberate choice: the requirement is "persist for the current
session," and `sessionStorage` is the browser primitive that means exactly
that — it survives a reload but clears when the tab closes, unlike
`localStorage`, which would silently outlive "the session." Each
`OverlayConfig` (`id`, `indicator`, `label`, `params`, `enabled`,
`colorIndex`) is a flat, plain-JSON-serializable record. `colorIndex` is
assigned once at creation from a monotonically increasing counter and never
reassigned — removing one overlay must not shift every remaining overlay's
chart/legend color. The store's shape was chosen so that a future "saved
workspace" feature is a persistence-backend swap (write this same shape to a
backend endpoint instead of `sessionStorage`, load it back into this same
store on open) rather than a redesign of the state or of any component that
reads it.

**Fetching: one batched query per chart, cache-aware.**
`useOverlayCalculations` sends only the **enabled** overlays, sorted by `id`
before being folded into the TanStack Query key — reordering the overlay
list must never produce a spuriously different cache entry. Disabling an
overlay removes it from the request entirely rather than fetching-and-hiding
it, so re-enabling it later either serves instantly from the backend's own
`IndicatorCache` (if the underlying candle range/params are unchanged) or
triggers exactly one fresh calculation — no separate frontend-side
calculation cache was built, since the batch endpoint plus the existing
`IndicatorCache` already provide "only recompute what changed" at the
compute layer, underneath whatever granularity the HTTP request happens to
use.

**Replay compatibility.** `ReplayChart` accepts the same
`overlays?: OverlaySeriesInput[]` prop and slices each overlay's `data` to
`tick.index + 1` inside a `useMemo`, mirroring exactly how
`useReplayChartSync` already reveals `candles` — an overlay is computed once
over the whole loaded session (the same "compute once up front" contract
candles already follow) and only _revealed_ progressively as the replay
clock advances, so an overlay can never show a value from beyond the current
replay position. `overlays` defaults to `[]`, so the existing Replay page is
unaffected unless a future change wires the panel into it.

**Where it's wired in today.** `HistoryPage` is the integration point: the
Indicator Panel sits beside the existing stats/quality/performance cards,
`useChartOverlays` (composition of `useOverlayCalculations` +
`toOverlaySeries`, colored via the shared `overlayColor` helper promoted
from `IndicatorChart`) feeds `ChartContainer`'s new `overlays` prop, and the
Indicator Legend renders alongside the chart view. The Replay and Live
Market charts already accept the same `overlays` prop end-to-end (proven by
tests) but are not yet wired to the panel/store — a future task, not an
engine change.

**Extension workflow.** Adding indicator #4, #40, or #400 to the overlay
system requires touching none of the above: register the indicator once
(`app/indicators/builtin/<name>.py` + registry, per "Technical Indicator
Engine" above) and it is immediately searchable in the Indicator Panel,
addable as an overlay, batchable, and chartable — the panel, the store, the
Overlay Engine, and the batch endpoint are all indicator-agnostic by
construction. The one caveat is intentional: `toOverlaySeries` flattens a
multi-series indicator's output to its first series for overlay purposes (a
single line is the only shape an "overlay on the candlestick chart" can
mean); MACD/Bollinger-style multi-series output remains fully usable on the
standalone `/indicators` page's own dedicated chart, which is unaffected by
any of this.

### Indicator Management & Chart Overlay System — Production-Readiness Review

A UX/scalability pass over the system above, adding researcher-facing
polish and one real caching improvement, with **zero breaking changes** to
the batch endpoint's original shape, the store's original actions, or any
existing indicator.

**Registry metadata model: additive-only, confirmed.** Two new fields were
added to close this review's search/discoverability gap, both following the
existing pattern (`version`/`author`/`complexity`/`warmup_description` were
already additive, defaulted fields on `IndicatorMetadata`):

- `IndicatorMetadata.aliases: tuple[str, ...]` (default `()`) — alternate
  names a search should also match (e.g. `sma` declares `("MA", "Moving
Average", "Simple MA")`). Every builtin indicator (SMA, EMA, WMA, RSI) was
  given a small curated set; a future indicator that declares none is
  simply matched on name/label/category/description alone, exactly as
  before this field existed.
- No category enum was introduced. Categories remain a free-form string on
  the backend — the frontend's `groupIndicatorsByCategory`
  (`lib/categorize.ts`) owns a **UI-only** canonical ordering (Trend,
  Momentum, Volatility, Volume, Oscillators, Statistical) with a case-
  insensitive match against it; any category outside that list (today's
  registry only populates `trend`/`momentum`) is title-cased and shown in
  its own "Other"-style group rather than dropped. This is what lets a
  future indicator with a brand-new category still render correctly with
  **no frontend schema change**, the same guarantee the "Extension
  workflow" section above already established for the engine side.

**Batch response: expanded calculation metadata, additive.**
`IndicatorBatchResponse` gained `candles_analyzed`, `database_time_ms`,
`engine_version`, and `generated_at` (shared by the whole batch — one
candle load, one engine, per the existing "share what's shared" convention
`timestamps` already followed); `IndicatorBatchItemResult` gained
`warmup_candles` and `execution_time_ms` (per-item, since each indicator in
a batch still runs, warms up, and is cached independently). `ENGINE_VERSION`
(`app/indicators/engine.py`) is a new module-level constant, versioning the
_execution pipeline itself_ — independent of any indicator's own
`IndicatorMetadata.version` — so a researcher comparing results across time
can tell whether the pipeline changed underneath them, not just an
indicator. None of this touches `calculate`'s (the single-indicator
endpoint's) response shape.

**Frontend: `overlay-colors.ts`, `overlay-series.ts`, and four new
components, all additive to the existing module.**

- **Manual color override** — `OverlayConfig.colorOverride?: string | null`
  (new, optional field — a persisted overlay from before this field existed
  simply has no override) takes precedence over the automatic `colorIndex`
  rotation via `resolveOverlayColor(theme, colorIndex, override)`
  (`overlay-colors.ts`). `OverlayColorSwatch` (new, shared by both the panel
  and legend) turns the previously-static color dot into a button opening a
  small palette (`overlayColorPalette` — a superset of the automatic
  rotation's colors) plus a "Reset to automatic" action, wired to the
  store's new `setOverlayColor(id, color | null)` action.
- **Drag-and-drop + keyboard reordering, render order = legend order** — the
  store's new `moveOverlayToIndex(id, toIndex)` action splices one overlay
  to a new position; the Indicator Legend exposes this via native HTML5
  drag-and-drop on each row **and** up/down icon buttons (native
  drag-and-drop alone would exclude keyboard-only users, which this
  codebase's existing accessibility conventions don't accept elsewhere).
  `CandlestickChart`'s Overlay Engine was extended to detect a **pure
  reorder** (same set of overlay ids, different sequence) versus an
  add/remove/toggle: since lightweight-charts paints series in the order
  they were _added_ to the chart, a reorder recreates every overlay series
  in the new order so paint (z-)order actually follows the legend — the one
  case where "avoid unnecessary redraws" correctly yields to "render order
  must match," verified by
  `recreates every series in the new order when overlays are reordered`.
  An unrelated add/remove/toggle still only touches the series that
  actually changed, exactly as before.
- **Calculation-detail tooltips** — `IndicatorLegend` and `IndicatorPanel`
  both surface Calculation Time, Cache Status, Dataset Size, Warmup Period,
  Engine Version, and Source Price per overlay via a reused `InfoTooltip`,
  sourced from `OverlayChartSeries.meta` (new, optional field on the
  existing type) — populated in `toOverlaySeries` from the batch response's
  new fields above.
- **Upgraded search and category grouping** — `matchesIndicatorSearch`
  (`lib/search-indicators.ts`, new) matches name, label, category, every
  declared alias, and the description, replacing the panel's original
  label/name/category-only filter. `groupIndicatorsByCategory` groups the
  (already-filtered) results under `ListSubheader`s in the canonical order
  described above.
- **Comprehensive per-indicator tooltips** — `toTooltipSections`
  (new, in `features/indicators/lib/indicator-knowledge.ts`) renders one
  indicator's full `IndicatorKnowledge` (Purpose, Formula, Interpretation,
  Typical Parameters, Advantages, Limitations, Common Use Cases) as
  `InfoTooltip` sections, reusing the exact same curated content the
  standalone `/indicators` page's `IndicatorInfoPanel` already renders —
  never a second copy of it — now shown beside each entry in the Available
  Indicators list.
- **Overlay-set export** — `OverlayExportMenu` (new) plus
  `lib/overlay-export.ts`'s pure CSV/JSON/clipboard builders, mirroring
  `features/indicators/lib/export.ts`'s shape for the standalone page's
  single-calculation export but unioning several overlays' (possibly
  differently-warmed-up) timestamps into one aligned table.
- **Improved loading/empty states** — the panel's catalogue loading state is
  now `Skeleton` rows (was plain text); a no-match search state now offers a
  one-click "Clear search"; the legend's empty state adds an icon and
  points a researcher at the panel.

**Frontend-side result reuse: `createOverlaySeriesCache`.** The batch
endpoint's own instrumentation plus the engine's `IndicatorCache` already
guaranteed "only modified indicators are _recalculated_" at the compute
layer (see the section above). This review closes the matching gap one
layer up, at the _redraw_ layer: TanStack Query's default structural
sharing already keeps an unchanged batch result's object reference stable
across refetches when its content is deep-equal, but `toOverlaySeries`
previously rebuilt every overlay's `data` array on every call regardless —
so even though the engine skipped recomputing an untouched indicator, its
chart line was still handed a brand-new array reference on every refetch,
defeating the Overlay Engine's own reference-equality redraw-skip.
`createOverlaySeriesCache()` (`lib/overlay-series.ts`) wraps the existing,
still-fully-tested `toOverlaySeries` in a per-chart `Map<overlayId,
{result, color, series}>`: an overlay whose result **reference** and
resolved color are both unchanged from the previous call returns the exact
same `OverlayChartSeries` object, `data` array included, so
`CandlestickChart`'s redraw-skip actually engages end-to-end — from "only
modified indicators are recalculated" at the engine, through to "only
modified overlays are redrawn" at the chart. One cache instance belongs to
one mounted chart (`useChartOverlays` creates it once via `useRef`) and
prunes an overlay's entry the moment it's disabled/removed, so it cannot
grow unbounded across a long research session.

### Data Collection

> To be completed in future tasks.

### Data Storage

> To be completed in future tasks.

### Feature Engineering Engine

`services/api/app/features/` is the platform's AI-readiness layer and its
BC3 bounded context (`docs/architecture/DomainModel.md`). Models do not
consume raw candles; they consume engineered feature vectors, and this is
where market data becomes them. As with the indicator engine, the design
optimises for adding hundreds of generators cheaply rather than for
shipping many today — eight ship now.

**Layering.** The same rule `app/indicators/` follows, for the same reason:
nothing in `app/features/` imports SQLAlchemy, FastAPI, or Pydantic, and no
generator may either. A generator receives plain `OHLCVPoint` values and
returns plain columns, which is what lets the same implementation serve the
REST API today and, unchanged, a training job or live inference path later.

```text
app/features/
├── base.py       FeatureGenerator ABC, FeatureContext/Output/Column, metadata
├── registry.py   FeatureRegistry (+ the app-wide default_registry)
├── pipeline.py   FeaturePipeline — the execution pipeline
├── dataset.py    FeatureDatasetBuilder — several generators into one matrix
├── export.py     CSV and JSON serialization
├── errors.py     Domain errors (all AppError subclasses)
└── builtin/      Auto-discovered generator modules
    ├── ohlcv.py             Raw OHLCV (5 columns)
    ├── candle_shape.py      Body, upper wick, lower wick, direction
    └── indicator_feature.py Adapter exposing any indicator as a feature
```

`app/services/features.py` is the only place the two halves meet, and
candle loading itself is shared with the indicator service via
`app/services/candle_points.py` — extracted once both needed the identical
"resolve the market, validate the timeframe/range/limit, run one ordered
query, project onto `OHLCVPoint`" sequence, because that is one operation,
not one per analytical context.

**Reuse over parallel implementation.** Two decisions matter more than any
other here, and both are about _not_ writing code:

1. **`OHLCVPoint` and `ParameterSpec` are imported from
   `app/indicators/`, not redefined.** A feature's input _is_ a candle and
   its parameters _are_ validated the same way an indicator's are. The
   pipeline calls the indicator engine's own `validate_parameters` and
   translates only the raised error type, so bounds, choices, coercion, and
   the "recommended: N" message exist once.
2. **SMA/EMA/WMA are not reimplemented.** `IndicatorFeature` wraps an
   already-registered indicator and delegates every computation to the
   shared `IndicatorEngine`, deriving its catalogue metadata from the
   indicator's. This is not a convenience — it is the mechanism that makes
   _training/serving consistency_ structural. If the maths were written
   twice, "SMA(20)" would eventually mean two different things, and a model
   would train on one definition while the chart showed another. That is
   training/serving skew, the exact failure BC3 exists to prevent
   ("Feature computation must be identical for training and inference").
   The consequences compound: every future indicator becomes a feature by
   adding its name to `INDICATOR_BACKED_FEATURES`, a fix to an indicator's
   maths fixes the feature in the same commit, and both share the
   indicator engine's result cache.

**Registry.** Name → generator instance, the single extension point.
Supports both `@register` over a class (a hand-written generator) and
`register_generator(instance)` for a _constructed_ one — the latter exists
for adapters: without it, reusing the indicator engine would have meant
hand-writing a near-identical subclass per indicator, duplicating exactly
the metadata the adapter derives.

**Execution pipeline.** One fixed sequence, no branch on which generator is
running:

```text
resolve → validate parameters → check warmup → generate → verify alignment → verify unique columns
```

Two stages exist to catch failures that would otherwise be silent:

- **Warmup check** — a range shorter than a generator needs raises
  `insufficient_data` (a 400 naming the shortfall) _before_ generation.
  Checking it here rather than leaving it to the generator matters: a
  delegating generator's own engine would otherwise raise inside the
  generic failure boundary and surface as an opaque 500 for what is
  plainly a bad request.
- **Alignment verification** — every column must have exactly one value per
  input candle. A misaligned column still serializes, still exports, and
  still trains a model — against the wrong timestamps. Checking centrally
  gives every generator the guarantee for free.

No result cache lives in the pipeline, unlike `IndicatorEngine`. A feature
request is a _dataset_ request whose output is proportional to the whole
range, and the expensive part (loading candles) already happens once
upstream; caching whole datasets would trade a lot of memory for a saving
already captured. Indicator-backed generators still get the indicator
engine's cache underneath.

**Dataset builder.** Owns the three things only it can see, because it is
the only component handed more than one generator at once:

| Concern                | Behaviour                                                                                                                                                                                                                   |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Column collisions      | Two features producing the same column name are rejected, naming both. A silently overwritten column means the model trains on data nobody intended, with nothing looking wrong.                                            |
| Warmup trimming        | Rows where _any_ requested feature is undefined are dropped by default — a training matrix cannot contain nulls, and imputing them is a modelling decision this layer must not make silently. The count is always reported. |
| Reproducibility record | Pipeline version, every feature's version, fully-resolved parameters, and the exact row accounting.                                                                                                                         |

Trimming drops _any_ incomplete row, not only leading ones: a null
mid-series (a flat candle's undefined normalized wick fraction) is as
unusable to a model as a leading one, and "complete rows only" is far
easier to reason about than a list of special cases.

**`limit` means rows, not candles.** The service widens its candle window
by the largest requested warmup before loading, then caps the built dataset
back to the requested row count. Without this, adding a longer-period
feature would silently shrink an existing dataset — the kind of quiet
change that makes results irreproducible. The caller's `limit` is validated
_before_ widening, so an over-limit request is rejected rather than clamped
and quietly under-served.

**Export is server-side, and separate from preview.** A preview is capped
so a browser can render it; an export is the complete dataset by
definition. They are two endpoints rather than one with a `format`
parameter, because conflating them is how a researcher exports the 200 rows
they happened to see and trains on a fraction of their data. `preview_rows`
is ignored by the export path, and the frontend strips it at the call site
too. Both formats carry the full provenance record; CSV writes it as `#`
comment lines so `read_csv(comment='#')` still works.

**Extension workflow.** Adding a generator is one file: create
`app/features/builtin/<name>.py`, subclass `FeatureGenerator`, declare
`metadata`, implement `generate`, decorate with `@register`. Nothing else
changes — not the pipeline, registry, builder, service, API, or frontend,
since the `/features` page renders its selector, parameter forms, and
column headers entirely from the catalogue response.

### Feature Engineering Engine — Production Hardening

A hardening pass over the system above, aimed at the platform's next
consumers — AI training, backtesting, paper trading, model evaluation — all
of which need a dataset to be **identifiable, reproducible, and honest about
its own quality**, not just correct. Every change here is additive: the
registry, pipeline, dataset builder, export layer, indicator engine, chart
components, and Zustand stores this review builds on are unchanged in shape;
nothing was rewritten or duplicated.

**Metadata model: five new fields, all additive-defaulted.**
`FeatureMetadata` gained `unit` (`""` default), `value_type` (`"float"`
default), `dependencies: tuple[str, ...]` (`()` default), `is_deterministic`
(`True` default), and `missing_values_expected` (`False` default) — every
existing generator's metadata still constructs with no changes required,
matching the same additive pattern the indicator review already established
for `aliases`/`version`/`complexity`. `dependencies` is the one field that is
also a real extension point, not just descriptive metadata: it feeds both
layers of dependency validation below. No shipped generator declares a
non-empty `dependencies` today — the field exists so a future generator that
_does_ need another feature's output has somewhere correct to say so.

**Dependency validation, two layers, two different failure modes.**

1. **Registry-wide, at startup.** `FeatureRegistry.validate_dependencies()`
   runs once, at the end of `load_builtin_features()`, over every registered
   generator: an unresolvable dependency name raises
   `UnknownFeatureDependencyError`, and a DFS over the whole dependency graph
   (`_check_cycle`) raises `FeatureDependencyCycleError` naming the exact
   cycle path. Both are plain `RuntimeError` subclasses, not `AppError` —
   this is a developer mistake in a generator's declared metadata, caught at
   import time, not a request the API should ever see.
2. **Request-scoped, per build.** `validate_feature_requests()`
   (`app/features/validation.py`) checks only that _this request's_ features
   carry their declared dependencies alongside them in the same request,
   raising `MissingFeatureDependencyError` (an `AppError`, 400, naming the
   missing feature) if not. This is deliberately simpler than graph
   traversal — presence-in-request, not reachability — because the registry
   check above already guarantees no cycle or dangling reference can exist
   in the first place; this layer only has to catch "you asked for the
   dependent but forgot the dependency."

**Partial-success dataset building — the largest single change.**
`FeatureDatasetBuilder.build()` previously aborted the whole dataset on the
first failing feature. It now mirrors the indicator engine's already-proven
batch-endpoint contract exactly: `FeatureNotFoundError`,
`InvalidFeatureParameterError`, `InsufficientFeatureDataError`, and
`FeatureExecutionError` are caught per-request and recorded as a
`FeatureFailure` in the dataset's quality report instead of raised, so one
bad feature in a ten-feature request no longer discards the other nine.
`required_warmup()` was changed to match — it now also swallows those same
four errors per request, since computing the warmup window is the first
thing `build()` does, and a request that will fail must not be allowed to
poison that calculation before the failure is ever recorded. Two error
classes still hard-fail immediately, because there is no partial result that
makes sense for them: `DuplicateFeatureColumnError` (two features colliding
on one output column) and `MissingFeatureDependencyError` (a structural
problem with the request itself, not a single generator's runtime failure).

**Dataset identity and versioning.** Every `FeatureDataset` now carries a
`dataset_id` (`uuid4()`, generated fresh per build) alongside its existing
`pipeline_version` and per-feature `version`s. It is deliberately **not** a
content hash: rebuilding an identical request a day later — over data that
may itself have changed (a corrected candle, a later `end`) — must yield a
distinguishable dataset, not silently collide with a stale one. `dataset_id`
answers "which specific build is this," not "is this data the same as
before"; the existing provenance fields already answer the latter.

**`DatasetQualityReport` (`app/features/quality.py`), new.** Every dataset
now carries a structured account of its own trustworthiness alongside its
data: `total_rows`/`rows_returned`/`rows_removed`, `null_counts` per column
(computed **before** warmup trimming, so a column whose nulls extend past
the warmup window is still visible), `duplicate_timestamps` and
`missing_candles` (both computed over the full, untrimmed candle series via
new `count_duplicate_timestamps`/`count_missing_candles` helpers —
`count_missing_candles` reuses the existing `resolution_duration` from
`app.services.candle_ingest` rather than re-declaring a timeframe table),
`feature_failures` (the partial-success record above), and
`generation_time_ms`. A dataset with zero successful features is now a
_valid_, fully-explained empty result (`quality.feature_failures` says why)
rather than the generic `EmptyDatasetError` it previously raised — that
error is now reserved for its original, narrower meaning: columns exist but
every row was legitimately trimmed as warmup.

**Export layer: format registry, so Parquet is one entry, not a refactor.**
`app/features/export.py` introduces `ExportFormat` (`extension`,
`media_type`, `binary`, `serialize`) and an `EXPORT_FORMATS: dict[str,
ExportFormat]` registry currently holding `csv` and `json`. Both
`FeatureService.export_dataset` and the API endpoint's format-pattern regex
derive from this registry rather than branching on format string — adding
Parquet later means adding one `ExportFormat` entry (binary output, a
different `serialize`) with no change to the service or endpoint.
`ExportedDataset.content` was widened to `str | bytes` in anticipation.
Every export now also carries the dataset's `dataset_id`, an `exported_at`
timestamp (distinct from the dataset's own `generated_at` — this one marks
when the file was written, not when the data was built), the pipeline
version, and the full quality summary; CSV writes these as `#`-prefixed
comment lines (including one `# feature.<name>,version=... params=(...)
columns=(...) warmup=...` line per feature and one `# quality.*` line per
metric), so `read_csv(comment='#')` still round-trips cleanly.

**AI extension points, documented and typed — two now have real
implementers (`app/features/ai_extensions.py`).** Originally six
`Protocol`/`dataclass` pairs mirroring the frontend's own established
precedent (`apps/dashboard/src/features/replay/extension-points.ts`) for
describing a future capability without building it prematurely. Two have
since been deleted from this file outright, not merely marked stale, once
fully superseded by a real implementation elsewhere: `LabelSpec`/
`LabelGenerator` (target/label generation) by the ML Dataset Builder's own
`TargetGenerator`/`TargetPipeline`, and `TrainValidationTestSplitter` by
`app/ml_datasets/split.py`'s `ChronologicalSplitter` (`SplitRatios`/
`DatasetSplit` are kept, imported and used unchanged by both this file and
`ChronologicalSplitter`). A third, `NormalizationStats`/`FeatureNormalizer`
(`fit`/`transform` kept as two separate methods, deliberately never
combined, so a normalizer fit on training data can never leak test-set
statistics into itself), is kept here as the live contract and has gained
its own first real implementer: `app/training/normalization.py`'s
`ColumnNormalizer` — see § "Machine Learning Training Framework" below for
why (Feature Importance and L2 regularization are otherwise scale-biased
toward large-magnitude features). Remaining genuinely unimplemented:
`WindowSpec`/`SequenceWindower` (sliding-window sequence generation) and
`CategoricalEncoding`/`CategoricalEncoder` (reads a column's declared
`dtype` rather than a hardcoded column list, so it generalizes to any future
categorical feature) — neither is imported by any production code path yet.

**Frontend: search, keyboard navigation, recently-used, and virtualization
— all additive to the existing `feature-engineering` module.**

- **Shared search matching, promoted once a second consumer needed it.**
  `matchesCatalogSearch` (`src/lib/search-catalog.ts`, new) is the indicator
  overlay panel's `matchesIndicatorSearch` logic (name/label/category/
  aliases/description) lifted out to a shared module — `search-indicators.ts`
  now delegates to it — the same "promote on second use" pattern already
  used for `group-by-category.ts`. `FeatureSelector` uses it for a search box
  plus a category filter (a real, visible MUI `label`, not just
  `aria-label` — a select with only `aria-label` and no visible label
  resolves to an empty accessible name, a recurring MUI gotcha in this
  codebase).
- **Roving keyboard navigation, no new dependency.** A single `onKeyDown` on
  the feature list reads `data-feature-name` off `document.activeElement`,
  finds its position in the currently-filtered visible list, and moves focus
  to the next/previous checkbox, wrapping at both ends.
- **Recently-used features**, session-scoped.
  `use-recent-features-store.ts` (new Zustand store, `persist` +
  `sessionStorage`) mirrors `use-overlay-store.ts`'s established
  session-scoped pattern exactly; `recordUsed(name)` moves an existing entry
  to the front rather than duplicating, capped at 8.
- **Two-card dataset display**, matching the backend's own provenance/quality
  split. `DatasetInfoCard` (new) shows identity and reproducibility —
  Dataset ID, Pipeline Version, Market, Timeframe, Rows, Columns, Generation
  Time. The existing `DatasetSummary` was extended, not replaced, to show
  trustworthiness — duplicate timestamps, missing candles, a null-columns
  alert, and a feature-failures alert — reading directly off the new
  `quality` object.
- **Manual table virtualization, no new dependency.** `DatasetPreviewTable`
  was rewritten to window its rows by scroll position (`ROW_HEIGHT = 33`,
  `TABLE_HEIGHT = 460`, `OVERSCAN = 8`) with two spacer `<TableRow>`s
  preserving correct scrollbar size — verified to mount far fewer than 200
  `<tr>` elements for a 100,000-row dataset and to re-window correctly on
  scroll, keeping the preview responsive regardless of dataset size.
- **Tooltips throughout.** Every technical term surfaced by this review
  (Warmup Rows, Feature Version, Pipeline Version, Dataset Version, Candle
  Direction, Body Size, Upper/Lower Wick, EMA, SMA, WMA) is explained via the
  existing, reused `InfoTooltip` component — never a new tooltip
  implementation.

### Feature Engineering Engine — Versioning, Lineage, Correlation, Cache, and Statistics

A fourth pass over the same system, entirely additive on top of the
Production Hardening pass above: **no change to the registry, pipeline
core, dataset builder's assembly logic, export layer, or any builtin
generator's `generate()`.** Every item below either surfaces data that
already existed (versioning), adds a pure read-only computation over an
already-built dataset (correlation, statistics, lineage), or adds an
optional, narrowly-scoped cache at the exact seam `IndicatorEngine` already
caches at (the Feature Cache).

**Feature Versioning — already fully implemented; this pass changed
nothing.** `FeatureMetadata.version` (per-generator semver),
`PIPELINE_VERSION` (pipeline-level), `FeatureDataset.dataset_id`, and
per-feature `DatasetFeatureInfo.version` were all already recorded and
echoed through `FeatureDTO`/`FeatureDatasetMeta`/`DatasetFeatureInfoDTO`
into every dataset response and CSV/JSON export (see the Production
Hardening pass above). The one gap was visibility, not existence: the
frontend's `DatasetSummary` chip row already showed `"{label} v{version}"`
per feature — now extended (see below) to also show cache status, rather
than adding a second, redundant versioning surface.

**Feature Lineage and Feature Dependency Graph — one shared module, not
two.** `app/features/lineage.py` (new) resolves
`FeatureMetadata.dependencies` — already declared and already validated at
startup by `FeatureRegistry.validate_dependencies()` — into a traversable
graph: `build_lineage_graph(registry)` returns every node's direct
dependencies, direct dependents (`depended_on_by`, the reverse edge, not
declared anywhere and derived here), the full transitive closure in both
directions (`ancestors`/`descendants`), the edge list, and a topological
order (a fresh DFS, `_topological_order`, conceptually mirroring
`FeatureRegistry._check_cycle`'s own three-color traversal but producing
an order rather than validating one — since the registry already
guarantees the graph is acyclic at startup, this only re-raises
`FeatureDependencyCycleError` defensively, for a hand-built registry that
was never validated). "Lineage" (what feeds one feature) and "dependency
graph" (the whole registry's structure) are deliberately the same
underlying edge set, read two ways, rather than two parallel graph
representations — exactly the duplication this platform's Strategy +
Registry contexts already avoid elsewhere. New endpoint: `GET
/features/lineage`, registered in the router **before**
`GET /features/{feature}` so the literal path `lineage` is never matched as
a `{feature}` path parameter. Honest current state: no shipped generator
declares a real dependency (`FeatureMetadata.dependencies` remains
`()` everywhere), so a real response today has zero `edges` — the graph,
cycle detection, and topological order are all real and already exercised
by the registry's own startup validation, simply over an edgeless graph
until a future generator declares one.

**Feature Correlation Matrix (`app/features/correlation.py`, new).**
`compute_correlation_matrix(columns, rows)` is a pure function over an
already-built `FeatureDataset` — the same "no second database query, use
what the builder already produced" discipline `quality.py` holds itself
to — computing pairwise Pearson correlation across numeric columns only
(`dtype in ("float", "int")`; a categorical column's "correlation" is
meaningless, the same gate `column-stats.ts`'s own `isNumericDtype` already
applies client-side). Uses pairwise-complete rows per column pair (skips a
row for one pair only if either of _that pair's_ values is `None`, not if
any value anywhere in the row is `None`) so a dataset built with
`drop_warmup=false` still produces a meaningful result. Returns an empty
result (`columns: []`) rather than raising when fewer than two numeric
columns are present — not an error, the same "gracefully absent, not a
placeholder" convention `RocPrCurveCharts` already established for a job
with no probabilities. New endpoint: `POST
/markets/{symbol}/features/correlation`, same request body as
`/features/dataset`, reusing `FeatureService.build_raw` wholesale (the
existing "one dataset-building path every consumer shares" contract, now
serving a third consumer alongside the dataset and export endpoints).

**Feature Statistics (`app/features/statistics.py`, new).** The backend
counterpart of the frontend's own preview-scoped `column-stats.ts`:
`compute_dataset_statistics(columns, rows)` reports `count`/`null_count`
for every column, plus `mean`/`std`/`minimum`/`maximum` (population
variance, the same formula `column-stats.ts` uses, so a value computed
here and a value the frontend's own preview popover shows for the same
column always agree) for numeric columns only — `None` for a
categorical/boolean column, never a fabricated number. Field names
(`mean`, `std`, `minimum`, `maximum`) deliberately match
`ai_extensions.py`'s `NormalizationStats`, though the two remain distinct
types: this is a full descriptive report over every column of an
already-built dataset, not a normalizer's fit-on-train-split statistics.
New endpoint: `POST /markets/{symbol}/features/statistics`, same request
body shape, also reusing `build_raw` — and, unlike the dataset endpoint's
own response, never capped by `preview_rows`, since it always describes
the complete dataset.

**Feature Cache (`app/features/cache.py`, new) — extends caching
coverage, does not reverse the pipeline's own prior decision.** The
Production Hardening pass's pipeline docstring correctly rejected caching
a _whole dataset_ (memory cost proportional to the requested range, and
the real cost — loading candles — happens once upstream regardless). This
is a different, narrower cache, at the same per-generator granularity
`IndicatorEngine` already caches at: `FeatureCache`/`FeatureCacheKey`
mirror `IndicatorCache`/`CacheKey` exactly (a bounded in-process LRU dict,
`hits`/`misses`/`entries` stats, not thread-safe by the same
single-event-loop assumption), reusing `fingerprint_candles` from
`app/indicators/cache.py` directly rather than a second candle-identity
implementation. `FeaturePipeline` gained an optional `cache: FeatureCache
| None` constructor argument; `run()` now checks it before generating
(mirroring `IndicatorEngine.run()`'s own resolve → validate → warmup check
→ cache lookup → generate → verify → cache store sequence) and records
`cache_status: "hit" | "miss" | "disabled"` on `FeatureRun`, threaded
through to `DatasetFeatureInfo`/`DatasetFeatureInfoDTO` (both fields
defaulted, so every existing direct construction of either dataclass keeps
working unchanged). `get_feature_pipeline()` now wires one process-wide
`FeatureCache()` in, alongside the already-shared `IndicatorEngine`.
Indicator-backed features (`sma`/`ema`/`wma`) already got caching for free
from that shared engine; this is what extends the same benefit to
`ohlcv`/`candle_shape` and any future non-indicator-backed generator. The
frontend's `DatasetSummary` feature chips now tint green on a cache hit
(via a `Tooltip` showing the exact execution time and cache status) rather
than adding a second, separate per-feature info table.

**Frontend: three new panels, one existing component extended, one route
change.** `FeatureCorrelationMatrix` (heatmap table, green/red `sx`
background-color intensity by correlation strength and sign — this
codebase's established "plain background color, not a charting library"
approach, the same convention `dataset-preview-table.tsx`'s own split-label
coloring already uses) and `FeatureStatisticsPanel` (a table, one row per
column) are both driven by `FeatureAnalysisPanel`'s single "Analyze" button
— triggering both `useComputeCorrelation`/`useComputeStatistics` mutations
together rather than two separate buttons, since both rebuild the same
dataset server-side and a researcher who wants one typically wants the
other. Deliberately **not** computed automatically alongside every dataset
build, which would silently double or triple the work for a researcher who
never opens this panel. `FeatureLineagePanel` renders the dependency graph
as a grouped list of chips (dependencies/dependents per feature, plus the
topological order as a sentence) rather than a drawn node-link graph — this
platform has no graph-drawing library, and every node has zero edges
today; this view is fully correct and immediately useful the day a real
dependency is declared, with no code change. `DatasetSummary`'s existing
feature-version chips gained the cache-status tint described above.

### Dataset Validation & Quality Engine

`services/api/app/dataset_validation/` is a mandatory quality gate that
sits _after_ the Feature Engineering Engine, never inside it: a dataset is
built exactly the way `/features/dataset` and `/features/export` already
build one, and only then handed to this engine's rules. Named
`dataset_validation` rather than `validation` deliberately — this platform
already has two other things reasonably called "validation"
(`app/features/validation.py`'s request-time feature-dependency check, and
`app/services/candle_validation.py`'s stored-candle integrity report, which
has no REST surface); this is a third, distinct concern with its own
registry, report schema, and API endpoint, and needed a name that could not
be confused with either.

**Reuse over parallel implementation — the same rule this platform has
applied twice already, applied a third time.** `FeatureService.build_raw`
(renamed from a private `_build` specifically for this) is the _one_
dataset-building path every consumer shares — `build_dataset`,
`export_dataset`, and now `DatasetValidationService.validate_dataset` all
call it. There is no second, parallel "build a dataset to validate it"
path that could quietly drift from the one everything else uses. Two
existing helpers are called directly rather than reimplemented a third
time: `count_duplicate_timestamps` and `count_missing_candles`
(`app/features/quality.py`), the same functions the dataset builder's own
`DatasetQualityReport` already uses — called here over the _delivered_
dataset (post-warmup-trim, post-`preview_rows`-cap) rather than the
pre-trim candle range the build-time report covers, which is a genuinely
different, still-useful scope: a caller who set `drop_warmup=false` gets a
report about the exact series a model would actually receive.

**Rule architecture: Strategy + Registry, a third application of the same
pattern `app/features/` and `app/indicators/` already establish.**

```text
app/dataset_validation/
├── base.py      ValidationRule ABC, ValidationContext/Issue, rule metadata
├── registry.py  ValidationRuleRegistry (+ the app-wide default_registry)
├── engine.py    DatasetValidator — runs rules, assembles the report
├── report.py    ValidationReport, ValidationSummary, CategorySummary
├── errors.py    Domain errors (AppError + startup-time RuntimeErrors)
└── rules/       Auto-discovered rule modules
    ├── structural.py     RequiredColumnsRule, DataTypesRule
    ├── data_quality.py   MissingValues, DuplicateRows, DuplicateTimestamps,
    │                     NaNValues, InfiniteValues
    ├── time_series.py    TimestampOrdering, TimeGaps
    └── feature_rules.py  MetadataConsistency, FeatureFailure
```

A `ValidationRule` receives a `ValidationContext` (the built `FeatureDataset`
plus an optional caller-supplied `required_columns` tuple — the one real,
tested extension point beyond the dataset itself) and returns zero or more
`ValidationIssue`s. **Adding a rule is one file**: subclass `ValidationRule`,
declare `metadata: ValidationRuleMetadata` (name, category, description,
default severity), implement `check`, decorate with `@register`. Nothing
else changes — not the engine, the registry, the service, the API, or the
frontend, since `/validation` renders its rule-catalogue panel entirely
from `GET /validation/rules`, exactly as `/features` renders its selector
from `GET /features`.

Only one registration style exists here (unlike the feature registry's
two) — no rule needs to _wrap_ an already-registered component the way
`IndicatorFeature` wraps an indicator, so there was nothing to build an
adapter mechanism for.

**Four categories, eleven builtin rules, matching every named check:**

| Category     | Rules                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------- |
| Structural   | `required_columns`, `data_types`                                                            |
| Data quality | `missing_values`, `duplicate_rows`, `duplicate_timestamps`, `nan_values`, `infinite_values` |
| Time-series  | `timestamp_ordering`, `time_gaps`                                                           |
| Feature      | `metadata_consistency`, `feature_failures`                                                  |

Two data-quality rules deliberately distinguish failure modes a single
"missing values" check would conflate: `nan_values` (a float `NaN` — a
computation defect, e.g. a division by zero) is not the same defect as
`missing_values` (a `None` — an intentional, reported absence, usually
warmup), and `infinite_values` is a third, distinct defect from either.
Conflating them into one check would report "something is wrong" without
saying what, which is not actionable.

**Severity is three-tier, exactly like a linter's:** `error`, `warning`,
`info`. `ValidationReport.passed` is `False` only when at least one `error`
was found — a `warning`/`info` finding is always reported but never blocks
the dataset. Two rules are deliberately `warning`-only even though they
found something real: `duplicate_rows` (a whole row repeating is _usually_
a red flag but occasionally expected — a flat market, say — so it should
be seen, not silently block a researcher) and `time_gaps` (a gap in the
delivered series is worth knowing about, but "the data has a hole" is a
different severity than "the data is corrupt"). Every other rule that can
fire at all defaults to `error`, since each represents a defect a model
should never train on.

**Validation report generation.** `DatasetValidator.validate()` runs every
registered rule (or a caller-chosen subset by name — an unknown name raises
`UnknownValidationRuleError`, a 404 naming every valid option) and
assembles a `ValidationReport`: `dataset_id`/`symbol`/`timeframe` (from the
dataset it validated), `engine_version` (the _execution pipeline's_ own
version, independent of any rule's, mirroring `PIPELINE_VERSION`/
`ENGINE_VERSION` elsewhere on this platform), `validated_at`, `passed`,
`rules_run`, a headline `summary` (total/errors/warnings/info), a
per-category `categories` breakdown (every category present at zero rather
than merely absent, so a UI never has to guess whether "time-series: 0" is
missing data or a clean bill of health), the flat `issues` list, and
`rows`/`columns`/`duration_ms`. Every field is JSON-serializable
(`app/schemas/dataset_validation.py` maps the Pydantic-free engine
dataclasses onto the wire, the same split `app/schemas/features.py`
already makes).

**API surface**, mounted beside the features endpoints it depends on
(`/markets/{symbol}/features/...`, not a new `/datasets/...` namespace —
one dataset-related URL family, not two):

| Method | Path                                         | Purpose                                                  |
| ------ | -------------------------------------------- | -------------------------------------------------------- |
| POST   | `/api/v1/markets/{symbol}/features/validate` | Build a dataset and run every registered rule over it    |
| GET    | `/api/v1/validation/rules`                   | Catalogue of every registered rule, for a rule-picker UI |

`POST .../validate`'s body is `DatasetValidationRequest` — a
`FeatureDatasetRequest` _subclass_ adding only `required_columns` and
`rules`, never a redeclaration of the market/timeframe/range/feature-list
fields. This is what lets the exact same selection that builds a dataset
also validate it: a caller changes the URL, not the shape of what they
send.

**Frontend** (`apps/dashboard/src/features/dataset-validation/`,
`/validation`): reuses the Feature Engineering page's own `DatasetForm` and
`FeatureSelector` outright rather than declaring a second dataset-selection
UI — the identical "reuse, don't duplicate" instruction this whole engine
was built under. `DatasetForm` gained optional `submitLabel`/`busyLabel`
props (defaulted to its original "Build Dataset"/"Building…" text, so every
existing caller is unaffected) so this page can relabel the same action
"Run Validation" without a second, near-identical form component.
`toDatasetRange` (the form's preset/custom-date-to-API-bounds conversion)
was promoted out of the Feature Engineering page's own local `toRange` into
`src/lib/resolve-dataset-range.ts` once this page needed the identical
conversion — the "promote on second use" pattern this codebase already
applies repeatedly (`group-by-category.ts`, `search-catalog.ts`). The page
renders: a Dataset Configuration section (the reused form plus an optional
comma-separated "Required columns" field), a Features section (the reused
selector), an "Available Checks" panel reading `GET /validation/rules` so
the rule catalogue is visible _before_ running anything, and — once
validated — summary cards (pass/fail, error/warning/info counts, a
per-category breakdown), an Error list and a Warning list (one shared
`ValidationIssueList` component parameterized by severity, not two near-
identical lists), Statistics (dataset id, rows/columns, rules run, duration),
and a Download action that serializes the report already in hand as JSON —
no second backend round-trip, since a validation report (unlike a feature
dataset) is never truncated in the first place.

### ML Dataset Builder

`services/api/app/ml_datasets/` composes the three engines above — Feature
Engineering, target generation (new), and Dataset Validation — into **the
only supported mechanism for producing a dataset used in AI training**. It
sits one layer above `dataset_validation` the same way that engine sits one
layer above the feature builder: nothing here recomputes a feature, revalidates
a rule, or re-splits a matrix that an existing component already owns.

**Targets are a fourth, deliberately _separate_ Strategy + Registry, not a
mode of the feature registry — this is the load-bearing leakage-prevention
decision, not incidental duplication.** A `TargetGenerator` (`base.py`) has
its own registry (`registry.py`), pipeline (`pipeline.py`), and builtin
package (`targets/`), structurally identical in shape to
`app/features/`/`app/indicators/`/`app/dataset_validation/`'s Strategy +
Registry pattern but living in a namespace a feature request can never
reach into. The consequence: there is no registry in which `"next_close"`
would resolve as a _feature_, which rules out the single worst mistake this
engine exists to prevent — training a model on its own label disguised as
an input column. Where a primitive genuinely is identical to an existing
one, it is reused rather than redeclared: `TargetColumn` is a direct type
alias of `FeatureColumn`, and `OHLCVPoint`/`ParameterSpec`/
`validate_parameters` are imported unchanged from the feature/indicator
modules that already define them.

**Mirror-image trimming is the structural core of leakage prevention.**
Features trim _leading_ rows (warmup — undefined at the start of a series);
targets trim _trailing_ rows (horizon — undefined at the end, since no
future candle exists yet to compute them from). A target is generated over
the **full, untrimmed** candle range — so a horizon lookup is always
reading a real future candle, never an out-of-range guess — and only
realigned onto the feature-warmup-trimmed matrix afterward, by matching
each surviving row's timestamp against the original series
(`index_by_timestamp`). `TargetPipeline._verify_forward_looking_contract`
then mechanically checks that the last `horizon` positions of every
returned column are `None`, rejecting with `TargetAlignmentError` any
generator — buggy or malicious — that fabricates a value it cannot possibly
know yet. This is independently enforced, not merely documented: a test
generator that fills in its own trailing window is used to prove the check
actually fires.

**Initial targets, one file each in `app/ml_datasets/targets/`:**

| Target           | Category    | Column               | What it predicts                                 |
| ---------------- | ----------- | -------------------- | ------------------------------------------------ |
| `next_close`     | `price`     | `next_close_{h}`     | The raw close price `h` candles ahead            |
| `next_return`    | `return`    | `next_return_{h}`    | Fractional change to the close `h` candles ahead |
| `next_direction` | `direction` | `next_direction_{h}` | `"up"` / `"down"` / `"flat"` classification      |

Every target shares one parameter, `horizon` (default `1`, declared once in
`targets/common.py` as `HORIZON_PARAMETER` and reused by all three rather
than redeclared). `next_return` guards a zero-close division explicitly
(returns `None` rather than `inf`/`NaN`), which is why it cannot reuse the
generic `shifted_column` helper the other two share.

**`MLDatasetBuilder.build()`** (`dataset.py`) is pure composition: the
_existing_ `FeatureDatasetBuilder` builds features, the new `TargetPipeline`
generates targets over the full range, targets are realigned and
trailing-trimmed, the combined matrix is handed to the _existing_
`DatasetValidator` (the identical cached singleton `/validation` uses — same
rules, same verdict contract), and finally to the new `ChronologicalSplitter`.
Targets are appended as ordinary columns onto the same `FeatureDataset.columns`/
`.rows` — not a parallel data structure — with `MLDataset.feature_columns`/
`.target_columns` (name tuples) tracking which is which, exactly matching
what `app/features/ai_extensions.py`'s own `LabelGenerator` docstring used
to anticipate before it was deleted (fully superseded by `TargetGenerator`
here — see § "AI extension points" above): "a label generator would add
exactly one more column to the same matrix." Partial-success mirrors the
feature/indicator batch contract
precisely — one failing target (`TargetNotFoundError`,
`InvalidTargetParameterError`, `InsufficientTargetDataError`,
`TargetExecutionError`) is recorded as a `FeatureFailure` rather than
aborting the build; a column-name collision (`DuplicateTargetColumnError`)
still hard-fails, since no partial result makes sense there.
`EmptyMLDatasetError` fires only when targets _were_ generated but zero rows
survive the horizon trim — zero target columns (every target failed
outright) is a valid result, not an error, mirroring the Feature Engineering
Engine's identical precedent for an all-failed feature request.

**Chronological, non-shuffled splitting.** `ChronologicalSplitter`
(`split.py`) is the one real implementer of the `split(dataset, ratios) ->
DatasetSplit` contract `ai_extensions.py` declared and left unwired in an
earlier task — that module's own `TrainValidationTestSplitter` Protocol has
since been deleted now that this is its one implementer, so the file states
one contract rather than two (see § "AI extension points" above); this
class reuses `ai_extensions.py`'s own `SplitRatios`/`DatasetSplit` rather
than redeclaring either. A split is three contiguous index slices of an
already-time-ordered matrix — train, then validation, then test, in that
order, never shuffled — and `dataset_id` stays identical across all three
slices, since "a split is a view over one build, not three independent
ones" (the same docstring `ai_extensions.py` already carried). Ratios must
be non-negative, train must be greater than zero, and the three must sum to
`1.0` within a `1e-6` floating-point tolerance, or `InvalidSplitRatiosError`
(400) is raised before any slicing happens.

**Versioning chain — the full reproducibility record for one build:**
`ml_dataset_id` (fresh UUID4, this artifact's own identity) sits atop the
embedded `FeatureDataset.dataset_id` (the underlying feature build's own,
separate identity); `ML_BUILDER_VERSION` (this composition's version) sits
alongside `PIPELINE_VERSION`, `TARGET_PIPELINE_VERSION`, and
`DatasetValidator.ENGINE_VERSION` — four independently-bumped version
numbers, each owning exactly the part of the pipeline it can change; each
target's own `TargetMetadata.version`; the exact `split_ratios` used; and
the embedded `ValidationReport` verdict. Rebuilding the identical request
later produces a new `ml_dataset_id` — a dataset is a snapshot, never a
live view.

**Export is one flat file, not three.** Both CSV and JSON emit the full
assembled (pre-split) matrix plus one additional per-row `split` column
(`"train"` / `"validation"` / `"test"`), reconstructed by concatenating the
three splits' row counts in original order — safe because rows are never
reordered anywhere in this pipeline. `app/ml_datasets/export.py` reuses
`app/features/export.py`'s helpers directly (`iso_utc`, `safe_filename_part`,
`csv_cell` — promoted from module-private names specifically for this reuse)
rather than reimplementing timestamp/filename/cell formatting a second time;
only the format-registry _pattern_ (`ExportFormat`), not the dataclass
itself, is repeated, since a Python dataclass field typed
`Callable[[FeatureDataset], str | bytes]` would be a type lie for
`MLDataset`.

**API surface**, mounted beside the endpoints it depends on:

| Method | Path                                         | Purpose                                                           |
| ------ | -------------------------------------------- | ----------------------------------------------------------------- |
| GET    | `/api/v1/ml/targets`                         | Catalogue of every registered prediction-target generator         |
| GET    | `/api/v1/ml/targets/{target}`                | One target generator's full metadata                              |
| POST   | `/api/v1/markets/{symbol}/ml/dataset`        | Build a versioned, split, validated ML dataset                    |
| POST   | `/api/v1/markets/{symbol}/ml/dataset/export` | Export the complete dataset (CSV/JSON) with a per-row split label |

`MLDatasetRequest` subclasses `FeatureDatasetRequest` — the same composition
`DatasetValidationRequest` already established — adding only `targets`
(≥1), `drop_undefined_targets` (default `true`), and `split_train`/
`split_validation`/`split_test`. The exact market/timeframe/range/feature
selection that builds a plain feature dataset also builds a fully versioned
ML dataset; a caller changes the URL and adds targets, nothing else.

**Frontend** (`apps/dashboard/src/features/ml-datasets/`, `/ml-datasets` —
a top-level route rather than the nested `/dashboard/ml/datasets` path,
the same deviation already made for `/features` and `/validation` and for
the identical reason: every other page lives at the `(dashboard)` route
group's top level, and this one should not be the first exception).
Reuses `DatasetForm` and `FeatureSelector` outright from Feature
Engineering, and `ValidationSummaryCards`/`ValidationReportPanel` outright
from Dataset Validation — the embedded verdict is the exact same
`ValidationReport` shape either page already renders, so a second
rendering component would only drift from the first. `DatasetPreviewTable`
(shared, not forked) gained two optional props — `targetColumns` (badges
and highlights label columns in the header/body so a researcher can tell
inputs from labels at a glance) and `splitLabels` (renders a trailing
"Split" column) — both `undefined` by default, so the Feature Engineering
page's existing usage is completely unaffected.

A second pass turned the page from a dataset _generator_ into a workbench,
still with no backend change:

- **`TargetSelector`** is a searchable multi-select (`Autocomplete`, the
  same widget `RequiredColumnsSelector` already uses) rather than a fixed
  checkbox list — each option shows the target's problem type
  (Classification/Regression, derived from `value_type` by
  `lib/target-type.ts`), description, output columns, and horizon
  compatibility range. Each selected target gets its own card with a
  **`HorizonPresetSelect`** — a preset dropdown (1/2/3/5/10/20/50 candles)
  plus a "Custom…" escape hatch — in place of a bare numeric field for the
  `horizon` parameter specifically; any other future parameter still falls
  back to the generic `ParameterForm`. The preset UI is presentation-only:
  every value it produces still flows through the same `validateValues`
  gate against the backend-published `horizon` spec before being
  committed, so the dropdown cannot introduce a value the backend would
  reject.
- **`SplitConfigForm`** gained a **`SplitTimeline`** — a proportional,
  chronologically-ordered bar (train, then validation, then test, left to
  right) with a percentage and, once a dataset has been built at least
  once, an estimated row count per split (computed client-side from the
  last build's `meta.total_rows`, not a second backend round-trip). The
  ratio fields themselves are unchanged (still 0–1 fractions, still
  validated by `validateSplitRatios`) — the timeline is a read-only view
  onto the same state, not a second source of truth. `validateSplitRatios`
  still deliberately allows a zero validation or test ratio, matching
  `ChronologicalSplitter`'s own tested backend behavior — this UI pass did
  not tighten that rule to "each split must be > 0" despite an initial ask
  to do so, since that would reject configurations the backend explicitly
  supports.
- **`MLDatasetMetadataPanel`** (new) — dataset UUID, feature pipeline
  version, source market/timeframe/date-range, generated timestamp,
  target generator(s), and the (currently singular) splitter name, plus
  the supported export formats. Its "Validation Report ID" field is
  honestly the embedded `ValidationReport`'s own `dataset_id` — the
  validation engine has no separate report-ID concept (`app/dataset_
validation/report.py`), so the panel says that rather than inventing a
  field the backend doesn't have.
- **`DatasetConfigActions`** (new) — "Copy Configuration" serializes the
  current market/timeframe/range/features/targets/split as JSON to the
  clipboard (`lib/dataset-config.ts`'s `serializeDatasetConfig`,
  degrading silently if clipboard access is unavailable, matching
  `validation-issue-list.tsx`'s existing Copy Issue pattern); "Import
  Configuration" opens a paste dialog, validates the pasted JSON with a
  Zod schema (`parseDatasetConfig`), and — only once valid — replaces the
  page's form/selection state. Import never builds anything on its own;
  the researcher still presses "Build ML Dataset" themselves afterward,
  exactly as if they had configured it by hand.
- **`ExportSummaryDialog`** (new) — CSV/JSON export no longer downloads
  immediately on click; it first shows rows, columns, target columns,
  split ratios, format, and an explicitly-labeled-as-approximate file-size
  estimate (`lib/export-format.ts`), so a researcher sees what they're
  about to get before committing. Export format buttons are rendered from
  `EXPORT_FORMAT_OPTIONS` data rather than hardcoded, so a future format
  needs no redesign of this dialog or `MLDatasetMetadataPanel`.
- **`DatasetPreviewTable`** (shared with Feature Engineering, extended
  again rather than forked) gained a column search box, a column
  visibility menu (hidden columns reset whenever the dataset's own column
  list changes shape, so a stale hide never survives a rebuild), a sticky
  first (Timestamp) column for horizontal scrolling through a wide matrix,
  and a per-numeric-column **`ColumnStatsPopover`** (min/max/mean/std/null
  count, computed via `feature-engineering/lib/column-stats.ts` over
  whatever rows are currently passed in — the popover says explicitly when
  that's only the rendered preview subset rather than the full dataset).
  `FeatureSelector` gained per-category Select All/Clear buttons
  alongside its existing global ones. Both changes benefit `/features` and
  `/validation` too, since all three pages share these components.

### Experiment Management System

The AI Research & Training bounded context's (BC4) registry — "what was
tried, over which dataset, with what configuration, and what happened."
Unlike the Feature Engineering/Dataset Validation/ML Dataset Builder
engines above it (all stateless request/response computations over
already-stored candles), this is the platform's **first genuinely
persistent, CRUD-backed domain**: an experiment is a real row, created
once and read/updated/deleted like any registry entry, not a value
computed fresh on every request.

**Entities**, matching `docs/database/DATABASE.md` § "Experiment
Management schema" exactly:

| Entity             | Table                  | Purpose                                                                           |
| ------------------ | ---------------------- | --------------------------------------------------------------------------------- |
| Experiment         | `experiments`          | Metadata, dataset version, feature/target/split config, model type, status, notes |
| Tag                | `experiment_tags`      | A normalized, indexable label — not a JSON array column                           |
| Metric             | `experiment_metrics`   | One recorded evaluation number (name, value, unit, timestamp)                     |
| Artifact reference | `experiment_artifacts` | A pointer (file path/filename/URL) to something the experiment produced           |

**Reuse over duplication, in the one place it actually applies here**:
`dataset_version`/`feature_set`/`target_config`/`split_config` are _not_
foreign keys into anything, because there is nothing to reference — the ML
Dataset Builder never persists a dataset row (§ "ML Dataset Builder"
above). An experiment copies the dataset's own `ml_dataset_id` and the
feature/target/split request shapes verbatim (mirroring
`MLTargetRequestItem`/`SplitRatiosDTO` field-for-field in
`app/schemas/experiments.py`, rather than redeclaring an incompatible
shape) — the same relationship a lab notebook has to the experiment it
describes: a citation, not a live reference.

**Tags are their own table, not a JSON column — the one new structural
decision this domain introduces.** Every existing table in this schema
(`exchanges`/`markets`/`candles`) is fully normalized with zero JSON
columns; a tag is exactly the kind of value that benefits from staying
that way, since `GET /experiments?tag=...` is then a real, indexed
`WHERE experiment_id IN (SELECT ...)` join rather than an in-application
scan over a growing blob. `feature_set`/`target_config`/`split_config` are
still stored as `JSON`, deliberately — they are genuinely a nested,
non-queried configuration snapshot, not something ever filtered or joined
on, so a real column would only add migration churn for schema shapes
that are already fully described (and versioned) upstream.

**No pluggable-engine pattern here, on purpose.** Feature/Target/Validation
are all Strategy + Registry because each has a genuinely open-ended set of
implementations a third party might add. An experiment record has a fixed
shape — there is nothing to register — so this domain is modeled the same
way `Market`/`Candle` already are: `app/models/experiment.py` (ORM),
`app/repositories/experiments.py` (all SQL, including search/filter/sort),
`app/services/experiments.py` (orchestration and domain errors,
mirroring `app/services/market_query.py`'s colocated-errors style), and
`app/schemas/experiments.py` (DTOs) — not a fourth registry.

**Search, filter, and sort** (`GET /experiments`) follow the exact
pagination/whitelisted-sort shape `GET /markets/{symbol}/candles` already
established: `sort`/`dir` are checked against a `SORT_COLUMNS` whitelist
(`name`, `status`, `model_type`, `created_at`, `updated_at`), raising the
same shape of `invalid_sort` (400) `InvalidSortError` already uses for
candles. `q` does a case-insensitive substring match against `name` OR
`notes`; `status`/`model_type`/`dataset_version` are exact-match filters;
`tag` filters via a subquery against `experiment_tags`. `limit`/`offset`
pagination returns `total` alongside the page, exactly like
`CandlePageResponse`.

**The experiment lifecycle is a status transition, not a delete-and-recreate.**
`status` moves `draft → running → completed | failed`, with `archived` as
an explicit "done looking at this" state — enforced as a `CHECK` constraint
at the database level (`ck_experiments_status_valid`) so an invalid status
can never reach storage regardless of which layer (Pydantic, the frontend
form) it might slip past. Full CRUD (including delete) is still supported
— `docs/architecture/DataArchitecture.md` § D9 describes experiment records
as "persistent and append-only" in the sense that a re-run never overwrites
a prior record's history (it gets a new row), not in the sense that a
researcher can never correct a mistake or remove a bad entry; this is the
same distinction `FeatureDatasetBuilder` already draws between "a dataset
is a snapshot, not a live view" and "you can still delete the row about it."

**API surface**, mounted like every other domain (both `/api/v1/*` and
unversioned):

| Method | Path                                               | Purpose                                         |
| ------ | -------------------------------------------------- | ----------------------------------------------- |
| POST   | `/api/v1/experiments`                              | Register a new experiment                       |
| GET    | `/api/v1/experiments`                              | Search/filter/sort/paginate                     |
| GET    | `/api/v1/experiments/{id}`                         | One experiment, with metrics and artifacts      |
| PATCH  | `/api/v1/experiments/{id}`                         | Partial update (only fields sent are changed)   |
| DELETE | `/api/v1/experiments/{id}`                         | Delete an experiment and its children (cascade) |
| POST   | `/api/v1/experiments/{id}/metrics`                 | Record a metric                                 |
| DELETE | `/api/v1/experiments/{id}/metrics/{metric_id}`     | Delete a metric                                 |
| POST   | `/api/v1/experiments/{id}/artifacts`               | Record an artifact reference                    |
| DELETE | `/api/v1/experiments/{id}/artifacts/{artifact_id}` | Delete an artifact reference                    |

A `PATCH` sending `tags` **replaces** the full tag set (not a merge) —
the same "the client sends the whole desired state for this one field"
contract `ChronologicalSplitter`'s split ratios use, chosen because a
partial tag merge has no obvious single correct semantics (add-only?
remove-only? both?) whereas "here is the new tag set" is unambiguous.

**Frontend** (`apps/dashboard/src/features/experiments/`, `/experiments`
and `/experiments/[id]` — the platform's first dynamic route). A list page
(search box, status/tag filters, a sortable/paginated table reusing
`TablePagination`/`TableSortLabel` exactly as `history/components/
candles-table.tsx` already does, and a create dialog) and a detail page
(an editable status select, an edit-toggling notes card, an always-live
tags editor, a metrics table with an inline add form, and an artifacts
list with an inline add form) — every mutation goes straight through the
same endpoints above, with no separate client-side draft state.

**Testing.** `tests/experiments/test_repository.py` and `test_service.py`
cover CRUD, search/filter/sort (including combined filters and pagination
math), and every partial-success/not-found error path;
`tests/api/test_experiments_api.py` covers the same surface end to end
over ASGI. 100% test coverage on every new backend module. See
`services/api/TESTING.md` § "Testing the Experiment Management System" and
`docs/testing/TESTING.md`'s frontend counterpart for the full test
inventory.

### Machine Learning Training Framework

The AI Research & Training bounded context's (BC4) orchestration layer,
sitting directly on top of Experiment Management: "run a training attempt
against an experiment, track its lifecycle, log its progress, and record
its outcome back onto that experiment." The framework's own machinery
(pipeline, lifecycle, registry, service, API) is model-agnostic by
design, so a future TensorFlow or PyTorch integration can be added
without touching any of it — see § "Baseline Model Framework" below for
the two real scikit-learn adapters now registered alongside the
placeholder, and how the pipeline was extended to load real training data
for them without changing its own six-stage shape.

**Entities**, matching `docs/database/DATABASE.md` § "Machine Learning
Training Framework schema" exactly:

| Entity       | Table               | Purpose                                                                                                                             |
| ------------ | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Training Job | `training_jobs`     | Which experiment, dataset citation, model adapter, hyperparameters, lifecycle status, current pipeline stage, error, result summary |
| Job Log      | `training_job_logs` | One line per pipeline-stage transition (or adapter-raised error)                                                                    |

**No pluggable-engine pattern for the job entity itself, for the same
reason `Experiment` isn't one**: a job record has a fixed shape. `app/models/
training.py` (ORM), `app/repositories/training.py` (all SQL), `app/services/
training.py` (orchestration, domain errors, and the composition point with
`ExperimentService`), and `app/schemas/training.py` (DTOs) — not a fourth
registry, mirroring `Experiment`'s own "registry, not a Strategy" choice.

**The model adapter _is_ a Strategy + Registry, on purpose — the one place
this domain genuinely is open-ended.** `app/training/base.py`'s
`ModelAdapter` (an abstract `initialize(hyperparameters)` /
`train(dataset, hyperparameters) -> TrainingResult` contract) and
`app/training/registry.py`'s `ModelAdapterRegistry` are the fourth
Strategy + Registry pair on this platform (after `FeatureGenerator`/
`TargetGenerator`/`ValidationRule`), because "which model actually runs" is
exactly the axis a future TensorFlow/PyTorch/scikit-learn integration needs
to plug into without changing anything else. `app/training/adapters/
placeholder.py`'s `PlaceholderModelAdapter` is the only adapter registered
today: it fabricates deterministic metrics (a function of `epochs`/
`learning_rate` only, never wall-clock time or randomness, so a re-run with
the same hyperparameters reproduces the same fabricated result) — it does
not read, load, or train on any real data.

**The job lifecycle is a state machine** (`app/training/state_machine.py`),
enforced in application code the same way `Experiment.status`'s _value set_
is enforced by a database `CHECK` constraint — this adds the _transition_
rule a `CHECK` constraint alone cannot express:

```text
pending -> running -> completed
                    -> failed
pending -> cancelled
running -> cancelled
```

`completed`/`failed`/`cancelled` are terminal. `status` is also `CHECK`-
constrained at the database level (`ck_training_jobs_status_valid`) to the
same five values, so an invalid status can never reach storage regardless
of which layer it slips past — the identical belt-and-suspenders design
`Experiment.status` already uses.

**The training pipeline** (`app/training/pipeline.py`'s `TrainingPipeline`)
is a fixed six-stage sequence, run by `POST /training-jobs/{id}/run`:

```text
validate_dataset -> load_dataset -> initialize_model -> execute_training -> save_results -> update_experiment
```

Framework-free by design, mirroring `app/features/pipeline.py`: the
pipeline never imports SQLAlchemy or FastAPI. Every stage is logged (start
and completion, or the exception on failure) through a small `log` async
callback; the DB-touching stages (`load_dataset`, `save_results`,
`update_experiment`) are each a callback hook the pipeline is given, not
something it does itself — `app/services/training.py`'s `TrainingJobService`
supplies the concrete implementations, the same separation `app/services/
ml_datasets.py` already draws between "the pure computation" and "the
database session that surrounds it." Runs **synchronously** within the
request — no worker/queue service exists anywhere on this platform yet, so
`/run` blocks for the (near-instant, since nothing real trains) duration
of the pipeline.

**`update_experiment` reuses `ExperimentService` directly — the one
integration point this whole framework exists to wire up.** A completed
job calls `ExperimentService.update(status="completed")`, then
`add_metric(...)` for every fabricated metric and `add_artifact(artifact_type=
"model_checkpoint", ...)` for the run's placeholder artifact — the _exact
same_ methods `POST /experiments/{id}/metrics` and `.../artifacts`
themselves call. A failed job (any stage raised) instead calls `update(status=
"failed")`, best-effort (a job whose experiment was independently deleted
mid-run still reports its own failure correctly; the experiment-update
failure is logged, not re-raised). Zero experiment-mutating SQL is
duplicated anywhere in this package.

**Logging** (`training_job_logs`): one row per stage transition, carrying
`level` (`debug`/`info`/`warning`/`error`), `stage`, and `message` — a
status monitor polling `GET /training-jobs/{id}` sees the full trail of
what the pipeline has done so far, in order, including exactly which stage
a failure occurred at.

**Result summaries**: `TrainingJob.result_summary` (JSON) holds the model
adapter's fabricated `metrics`, `artifact_uri`, and free-form `summary` —
written once, at the `save_results` stage, before the same numbers are
copied onto the experiment at `update_experiment`.

**API surface**, mounted like every other domain (both `/api/v1/*` and
unversioned):

| Method | Path                                | Purpose                                   |
| ------ | ----------------------------------- | ----------------------------------------- |
| GET    | `/api/v1/training-jobs/models`      | The model adapter catalogue               |
| POST   | `/api/v1/training-jobs`             | Register a new job (starts `pending`)     |
| GET    | `/api/v1/training-jobs`             | Search/filter/sort/paginate               |
| GET    | `/api/v1/training-jobs/{id}`        | One job, with its full log trail          |
| DELETE | `/api/v1/training-jobs/{id}`        | Delete a job (409 if currently `running`) |
| POST   | `/api/v1/training-jobs/{id}/run`    | Execute the pipeline synchronously        |
| POST   | `/api/v1/training-jobs/{id}/cancel` | Cancel a `pending` (or `running`) job     |

**Frontend** (`apps/dashboard/src/features/ml-training/`, route
`/ml/training`). A job list (experiment/status filters, a sortable/
paginated table reusing `TablePagination`/`TableSortLabel` exactly as
`experiments-table.tsx` already does) and a create dialog with an
Experiment selector (an `Autocomplete` over `GET /experiments`), a Dataset
selector (a text field defaulting from the selected experiment's own
`dataset_version`), a Model Type selector (populated from `GET
/training-jobs/models`, never free text — the one field this domain
constrains to a real registry), and a generic key/value Hyperparameter
editor (generic because each model adapter defines its own hyperparameter
space; the framework has no fixed schema to build a typed form against). A
detail dialog is the status monitor: current status/stage/timestamps, the
full log trail, the result summary once completed, and Run/Cancel/Delete
actions — it polls every 3s while `status === "running"`, since the run
itself has no independent push channel.

**Testing.** `tests/training/` covers the state machine (every legal/
illegal transition), the model adapter registry and the placeholder
adapter's determinism, the pipeline (every stage in order, and every
failure mode, with plain async stub hooks — no database), the repository
(CRUD/search/filter/sort/logs), and the service (lifecycle, pipeline
execution, and the experiment-integration path, including the
best-effort failure path); `tests/api/test_training_api.py` covers the
same surface end to end over ASGI; `tests/repository/test_training_postgres.py`
(opt-in, `postgres` marker) exercises the real `ON DELETE CASCADE` the
in-memory SQLite test engine cannot. 100% test coverage on every new
backend module. See `docs/testing/TESTING.md` for the full inventory.

### Baseline Model Framework

Professional quantitative research starts with baseline models — every
advanced model this platform eventually adds must be able to outperform
a simple linear one, or it isn't earning its complexity. This is the
first genuinely real training capability on the platform, built entirely
as new `ModelAdapter` implementations plus one new bridge module — the
Machine Learning Training Framework's job lifecycle, pipeline, registry,
service, and API needed **zero changes** to support it.

**Model interface** (`app/training/base.py`). `ModelAdapter` gained a
third abstract method, `predict(artifact_uri, rows) -> list`, alongside
`initialize`/`train` — training and prediction are deliberately decoupled:
`predict` loads whatever `train` serialized, assuming nothing about
in-memory state a training run left behind, since a prediction may run in
a different process, long after the job that produced the model finished.
`ModelAdapterMetadata` gained `model_kind` (`"placeholder" |
"classification" | "regression"`) and `requires_real_data: bool` — the two
facts the frontend and `TrainingJobService` each need to know about an
adapter without running it: which evaluation view to render, and whether
a job needs a real market/timeframe to build a dataset from at all.
`TrainingDataset` gained optional `train`/`validation`/`test: SplitMatrix
| None` fields (`SplitMatrix` = plain `X: list[list[float]]` / `y:
list[Any]`, no numpy import — this module stays framework-free, matching
`FeatureGenerator`'s own "framework-free inputs" discipline) — `None` for
the placeholder, populated for a `requires_real_data` adapter.

**Model registry** (`app/training/registry.py`) — unchanged. The two new
adapters register into the exact same `ModelAdapterRegistry` the
placeholder already uses, via the same `@register` decorator and the same
`load_builtin_model_adapters()` discovery loader
(`app/training/adapters/__init__.py`), so `GET /training-jobs/models`
lists all three with no endpoint change.

**Logistic Regression plugin** (`app/training/adapters/
logistic_regression.py`) — `sklearn.linear_model.LogisticRegression`,
`model_kind="classification"`. Trains on the built train split, evaluates
on validation (accuracy/precision/recall/F1, `average="weighted"`,
`zero_division=0`) and, if present, test; records a confusion matrix and
class labels in `summary`. Hyperparameters: `max_iter` (default 200), `C`
(default 1.0), `random_seed` (default 42). Pairs naturally with a
categorical target such as `next_direction`.

**Linear Regression plugin** (`app/training/adapters/
linear_regression.py`) — `sklearn.linear_model.LinearRegression`,
`model_kind="regression"`. Same train/validation/test evaluation shape,
reporting MAE/MSE/RMSE/R² and recording learned coefficients/intercept in
`summary`. Hyperparameter: `fit_intercept` (default `true`). Requires a
numeric target such as `next_close`/`next_return` —
`IncompatibleTargetDtypeError` if given a categorical one instead.

**Training integration** (`app/training/dataset_loader.py`,
`app/services/training.py`). `TrainingJob` gained three new nullable
columns — `symbol`, `timeframe`, `target_column` (migration
`ed0d4f9becf1`) — the concrete market/timeframe/target a real adapter
needs, which an `Experiment` has no reason to carry (it only cites a
`dataset_version` by value). `TrainingJobService`'s `load_dataset` stage
now checks the resolved adapter's `requires_real_data`: `false` keeps the
original citation-only behavior; `true` builds a real `MLDataset` by
calling `MLDatasetService.build_ml_dataset` (a new public method wrapping
that service's existing, private `_build` — the _exact_ same code
`POST /markets/{symbol}/ml/dataset` itself runs, never a second
dataset-building path) using the linked experiment's own recorded
`feature_set`/`target_config`/`split_config`, then hands the result to
`build_training_dataset` (`dataset_loader.py`) to resolve a target column
(defaulting to the first one built), restrict feature columns to numeric
dtypes (`float`/`int`/`bool` — a `"categorical"` feature column is
excluded; encoding one is `app/features/ai_extensions.py`'s documented,
not-yet-implemented `CategoricalEncoder` extension point), and reshape
each split into a `SplitMatrix`.

**Feature normalization** (`app/training/normalization.py`) — corrects a
real scale bias, not just a missing capability. `TrainingJobCreateRequest.
normalize_features` (default `true`) drives `build_training_dataset` to fit
`ColumnNormalizer` (z-score default, min-max also implemented) on
`ml_dataset.split.train` alone — never validation/test, the same
look-ahead-bias discipline chronological splitting already holds itself
to — and apply it to all three splits before they become numeric
`SplitMatrix`es. Without it, a feature naturally measured in the thousands
(`close`, `sma_20`) needs only a tiny raw coefficient to matter as much as
an equally predictive feature measured in single digits (`candle_body`)
needs a much larger one, so `compute_feature_importance`'s mean
|coefficient| ranking is scale-biased and L2 regularization (`C`)
implicitly under-penalizes large-magnitude features for the identical
reason. `TrainingDataset` gained `normalization: list[NormalizationStats] |
None` and `normalization_method: str | None` fields (`NormalizationStats`
imported from `app/features/ai_extensions.py`, not redeclared — see § "AI
extension points" above); both adapters record them onto `TrainingResult.
summary` (`normalization`/`normalization_method`, JSON-plain via
`normalization_stats_to_dicts`) and tag every `compute_feature_importance`
row with `normalized: true/false`, so a raw (scale-biased) report and a
normalized (scale-comparable) one are never confused —
`FeatureImportancePanel` surfaces this as a "Coefficients on normalized
features" caption. `TrainingJobService.predict` reconstructs the persisted
stats and applies the identical transform to a caller-supplied row before
predicting, via the free function `apply_normalization` (the same
per-value transform `ColumnNormalizer.transform` uses, over a plain numeric
matrix instead of a whole `FeatureDataset` — a live prediction request has
no columns/timestamps to carry). Deliberately training-time-only:
`FeatureDatasetRequest`/`FeatureDatasetResponse` and every ML Dataset
Builder export/history entry stay raw and human-readable, matching this
platform's existing "no server-side transform a researcher can't inspect"
convention (`docs/api/API.md`). Migration `d58d9f8bdab6` adds the
`normalize_features` column (`NOT NULL DEFAULT true`).

**Prediction interface** — `POST /training-jobs/{id}/predict`, new. Takes
`{"rows": [[...], ...]}` (each row already restricted to the job's own
`feature_columns`, recorded in `result_summary`), loads the completed
job's serialized model via the adapter's own `predict`, and returns
`{"predictions": [...], "feature_columns": [...]}`. Only available once a
job has `status="completed"` and recorded an `artifact_uri`
(`PredictionNotAvailableError` otherwise); a row-length mismatch is
rejected with `InvalidPredictionInputError` before ever reaching the
adapter. A caller-supplied row is normalized identically to how the job's
own training data was, immediately before this step, if the job was
trained with `normalize_features=true` — see "Feature normalization" above.

**Model serialization abstraction** (`app/training/serialization.py`).
`ModelSerializer` is a two-method protocol (`save(model, name) -> uri`,
`load(uri) -> model`) behind which `LocalDiskModelSerializer` writes a
fitted estimator to `Settings.model_artifact_dir` (default
`var/model_artifacts/`, gitignored) via `joblib.dump`/`joblib.load` — this
platform has no object storage wired in yet (§ "Known Limitations"). A
future S3/object-storage-backed serializer implements the same protocol
and swaps in behind `default_serializer` with no adapter change. `train()`
calls `.save()` and returns the resulting `file://` URI as
`TrainingResult.artifact_uri` — the _same_ field the placeholder adapter
already fabricates a `placeholder://` URI for, so `update_experiment`'s
`add_artifact(artifact_type="model_checkpoint", ...)` call needs no
change to record a real one.

**Metrics collection** — reuses the existing mechanism outright.
`TrainingResult.metrics` (now real: accuracy/precision/recall/F1 or
MAE/MSE/RMSE/R², not fabricated numbers) flows through the same
`save_results`/`update_experiment` pipeline stages already built for the
placeholder, landing in `TrainingJob.result_summary` and, on success, as
real `ExperimentMetric` rows via `ExperimentService.add_metric` — zero new
persistence code.

**Extension workflow for a future adapter**: subclass `ModelAdapter`,
declare `metadata` (including `model_kind` and `requires_real_data`),
implement `initialize`/`train`/`predict`, add one file under
`app/training/adapters/`, and `@register` it. If it needs real data, use
`dataset.train`/`validation`/`test` (already-built `SplitMatrix`es); if
not, ignore them exactly as the placeholder does. No pipeline, service,
repository, or API code changes are needed either way — the same
extension guarantee every Strategy + Registry context on this platform
already makes.

**Testing.** `tests/training/test_dataset_loader.py` covers target/
feature-column resolution and every failure mode (unknown target column,
no numeric feature columns, an empty split, a dtype-incompatible target,
an unexpectedly-undefined value) using a real `MLDatasetBuilder` over
synthetic candles — no database — plus a `TestNormalization` class proving
stats are computed from the train split alone and that a normalized train
split lands at ~0 mean/~1 std. `tests/training/test_normalization.py`
covers `ColumnNormalizer`/`apply_normalization` directly: fit-uses-only-
its-own-dataset, z-score/min-max transform correctness, and the
zero-variance-returns-0.0-not-NaN degenerate case. `tests/training/
test_serialization.py` covers the local-disk save/load round trip.
`tests/training/test_logistic_regression.py`/`test_linear_regression.py`
cover each adapter's `initialize`/`train`/`predict` in isolation
(deterministic, perfectly-fittable synthetic data, so metrics are exact)
plus scikit-learn failure wrapping — the former's
`TestFeatureImportanceScaleBias` is the concrete, real-sklearn proof of the
scale-bias fix: two independent, equally-informative, differently-scaled
features rank hugely disparately (>150x) by raw |coefficient| and land at
near-parity once normalized. `tests/training/test_service.py` and
`tests/api/test_training_api.py` each add a full real-data path end to
end — real candles seeded into the database, a real feature/target build,
a real `fit`, real recorded metrics/confusion-matrix, and a real
prediction — alongside the missing-symbol/missing-config/incompatible-dtype
failure paths, plus (`test_service.py`) a test proving `predict` applies
the exact persisted normalization transform to a raw row before predicting,
byte-for-byte matching a manual replication that bypasses the service
entirely. 100% test coverage on every module in `app/training/`. See
`docs/testing/TESTING.md`/`services/api/TESTING.md` for the full
inventory.

### Model Evaluation & Benchmarking Engine

Before this milestone, each real model adapter
(`logistic_regression`/`linear_regression`) computed its own
accuracy/precision/recall/F1 or MAE/MSE/RMSE/R² inline, with no shared
code between them — a pattern that does not scale to a third, fourth, or
tenth model family. This engine is the platform's **sixth** instance of
its Strategy + Registry pattern (after feature generators, indicators,
prediction targets, dataset validation rules, and model adapters
themselves): a `Metric` is a small stateless class declaring `metadata`
(name, category, direction) and a `compute(y_true, y_pred, y_proba)`
method, registered via `@register` into a `MetricRegistry` that mirrors
`ModelAdapterRegistry` exactly (`register`/`get`/`has`/`names`/
`describe_all`/`for_category`, a process-wide `default_registry`).

**Package layout** (`app/evaluation/`) — framework-light and
database-free throughout, the same discipline `app/training/pipeline.py`
holds itself to:

- `base.py` — `MetricMetadata` (`name`, `label`, `description`, `category:
"classification" | "regression"`, `higher_is_better: bool`,
  `requires_probabilities: bool`, `version`), `MetricResult` (a value, or a
  `skipped_reason`), `EvaluationReport` (a list of results, plus `.metrics`
  — the same flat `{name: value}` dict shape `TrainingResult.metrics` has
  always used, and `.skipped` — `{name: reason}`), and the `Metric` ABC.
- `registry.py` — `MetricRegistry`, an exact mirror of
  `app/training/registry.py`'s `ModelAdapterRegistry`.
- `metrics/classification.py` — `AccuracyMetric`, `PrecisionMetric`,
  `RecallMetric`, `F1Metric` (all `average="weighted"`, `zero_division=0`,
  `higher_is_better=True`) and `RocAucMetric` (`requires_probabilities=True`,
  `higher_is_better=True`; binary case uses the positive-class probability
  column, multiclass case uses `roc_auc_score(..., multi_class="ovr",
average="weighted")` — the same distinction `compute_roc_pr_curves`
  already makes for the confusion-matrix/curve report, now centralized here
  too).
- `metrics/regression.py` — `MaeMetric`, `MseMetric`, `RmseMetric` (all
  `higher_is_better=False`) and `R2Metric` (`higher_is_better=True`), each a
  thin wrapper over the equivalent `sklearn.metrics` function.
- `engine.py` — `EvaluationEngine.evaluate(model_kind, y_true, y_pred,
y_proba=None) -> EvaluationReport` runs every registered metric whose
  `category` matches `model_kind`. A metric that raises, or that declares
  `requires_probabilities=True` when `y_proba` is `None`, is recorded as
  **skipped** with a reason rather than aborting the rest — the same
  partial-success contract every other engine on this platform already
  holds itself to (e.g. `candle_validation`'s per-check independence). An
  unrecognized `model_kind` (e.g. `"placeholder"`) returns an empty report,
  not an error. `default_engine`, built over `default_registry`, is the one
  shared instance every real adapter imports.
- `benchmark.py` — `compare(candidates, metric_registry) -> BenchmarkResult`.
  `BenchmarkCandidate` is a plain dataclass (training job id, experiment id/
  name, model type/kind, dataset version, target column, completed-at, and
  its recorded `metrics` dict) — this module never touches SQLAlchemy or
  `TrainingJob`; the service layer builds these from already-persisted rows.
  For every metric name appearing on at least one candidate, `compare` picks
  the max- or min-scoring candidate according to that metric's registered
  `higher_is_better` (defaulting to `True`, conservatively, for an
  unregistered/unknown metric name rather than excluding it silently).
- `errors.py` — `MetricNotFoundError` (404), `DuplicateMetricError`
  (startup-only, mirrors `DuplicateModelAdapterError`),
  `NoBenchmarkTargetError` (400 — a benchmark request naming none of
  `dataset_version`/`target_column`/`experiment_ids` has nothing to match),
  `EmptyBenchmarkError` (404 — a well-formed request matching zero completed
  jobs).

**No new persistence.** A benchmark comparison is a **read-only** view over
data that already exists: `TrainingJob.result_summary["metrics"]`, written
by the unchanged `_make_save_results_hook`, and copied onto the linked
`Experiment` as real `ExperimentMetric` rows by the unchanged
`_make_update_experiment_hook` — see § "Machine Learning Training
Framework" above. There is deliberately no new "evaluation run" table;
`app/services/evaluation.py`'s `EvaluationService.benchmark` queries
`TrainingJobRepository.search()` (extended with two new optional filter
fields, `dataset_version`/`target_column`, on the existing
`TrainingJobFilters` dataclass — no new query method) for every
`status="completed"` job matching the request, further narrows by
`experiment_ids` if given, resolves each job's `model_kind` via the
existing `ModelAdapterRegistry` (falling back to `"unknown"` for a
model_type no longer registered), looks up each distinct experiment's name
through the unchanged `ExperimentService.get`, and hands the resulting
`BenchmarkCandidate` list to `app.evaluation.benchmark.compare`. A
completed job that recorded no metrics (e.g. the placeholder adapter) is
excluded from the comparison rather than shown as an empty row.

**Adapter refactor.** `logistic_regression.py`/`linear_regression.py` no
longer compute metrics inline — each now calls
`evaluation_engine.evaluate(self.metadata.model_kind, y_true, y_pred,
y_proba)` and reads `.metrics` off the report, for the validation split,
the train split, and (when present) the test split alike. This is a
refactor to a shared engine, not a behavior change: every previously
recorded metric value is unchanged, and `roc_auc` is a genuinely new
headline metric now appearing in `metrics`/`train_metrics`/`test_metrics`
for a classification job (previously only a per-class AUC existed inside
`roc_pr_curves`).

**API** — `GET /evaluation/metrics` (the full registered catalogue —
`MetricMetadataDTO` per entry) and `POST /evaluation/benchmark` (accepts
`dataset_version`/`target_column`/`experiment_ids`, at least one required;
returns every matched `BenchmarkCandidateDTO` plus a `BenchmarkBestEntryDTO`
per metric) — see `API.md` § "Model Evaluation & Benchmarking Engine" for
the full request/response shapes and error codes.

**Extension workflow for a future metric**: subclass `Metric`, declare
`metadata` (including `category` and `higher_is_better`), implement
`compute`, add one file under `app/evaluation/metrics/`, and `@register`
it. No engine, service, repository, or API code changes are needed — the
metric appears in `GET /evaluation/metrics`, runs automatically for every
job of its category, and participates in every future benchmark
comparison, the same extension guarantee every Strategy + Registry context
on this platform already makes.

**Frontend** (`apps/dashboard/src/features/ml-evaluation/`, `/ml/evaluation`
— full detail in `FRONTEND.md` § "Model Evaluation & Benchmarking Engine"):
a benchmark filter bar (dataset version, target column, a multi-select
experiment picker), a model comparison table (one row per matched job, one
column per metric, the winning cell per column highlighted), a best-model
summary (one card per metric, naming the winning model), small inline SVG
bar charts per metric (this codebase's established "small on-page chart,
not a charting library" approach), and a standing metric-catalogue
reference table. There is no separate persisted "evaluation history" —
the comparison table's own `completed_at`-descending ordering over
already-real training jobs is that history.

**Testing.** `tests/evaluation/` covers every metric in isolation
(including the binary/multiclass ROC-AUC split and the direct-call guard
when `y_proba` is omitted), the registry (register/duplicate/not-found/
`for_category`), the engine's partial-success contract (a raising metric,
a probability-requiring metric with none given, both skipped rather than
propagated), `compare` (correct winner per direction, the unregistered-
metric fallback, an empty-candidates no-op), and the service layer (both
`NoBenchmarkTargetError`/`EmptyBenchmarkError` paths, narrowing by
`experiment_ids`, an `"unknown"` `model_kind` for an unregistered
`model_type`). `tests/api/test_evaluation_api.py` adds the same benchmark
flow end to end over ASGI, training two real jobs and comparing them.
100% test coverage on every module under `app/evaluation/` and on
`app/services/evaluation.py`. See `docs/testing/TESTING.md`/
`services/api/TESTING.md` for the full inventory.

### Model Evaluation & Benchmarking Engine — Production-Readiness Pass

A follow-up pass over the engine above, entirely additive: **no change to
`EvaluationEngine`, `MetricRegistry`, the metric registrations, the
training pipeline, the adapter registry, or the model serialization
abstraction.** Every addition below either (a) surfaces data a training run
already produced, through a widened `BenchmarkCandidate`, or (b) adds one
new, narrowly-scoped persisted table for history — nothing recomputes a
metric, a confusion matrix, or a curve a second time.

**`BenchmarkCandidate` widened, read-only** (`app/evaluation/benchmark.py`).
Six new optional fields, all sourced from data the training job's own
`result_summary` already carries — `app/services/evaluation.py`'s
`benchmark()` populates them once per candidate, no new computation:

- `symbol`/`timeframe` — read straight off the `TrainingJob` row itself.
- `feature_count`/`sample_count` — read from `result_summary["model_metadata"]`
  (`app/training/model_metadata.py`'s `collect_model_metadata`, already
  computed at training time).
- `model_artifact_url` — the exact same deterministic
  `/training-jobs/{id}/artifacts/model_joblib` path
  `TrainingArtifactDTO.build` already computes for the Artifact Management
  panel, built here from the same `(job_id, "model_joblib")` pair whenever
  `result_summary["artifact_uri"]` is present — `None` otherwise (a
  completed job need not have produced a savable artifact).
- `report` — the job's own `result_summary` dict, **verbatim**. This is the
  one field that lets the frontend show a candidate's confusion matrix,
  ROC/PR curves, feature importance, and prediction samples without this
  engine (or the frontend) recomputing any of them — see "Visualization
  architecture" below.

**Visualization architecture — reuse, not reimplementation.** The frontend
(`apps/dashboard/src/features/ml-evaluation/components/
candidate-detail-dialog.tsx`) renders one candidate's full detail by handing
its `metrics` and `report` straight to `EvaluationSummary` — the _exact_
component `/ml/training`'s own job detail dialog already uses
(`apps/dashboard/src/features/ml-training/components/evaluation-summary.tsx`),
imported across features rather than copied (the same cross-feature-import
convention `create-training-job-dialog.tsx` already established by
importing `useExperiment` from the `experiments` feature). `EvaluationSummary`
itself is unchanged: it already renders a raw confusion-matrix grid, the
per-class `ConfusionMatrixDetailsTable`, and `RocPrCurveCharts` (ROC **and**
Precision-Recall together, one component) for a `model_kind: "classification"`
result, and gracefully renders neither for a regressor or an unrecognized
kind — "gracefully hide when probabilities are unavailable" was already this
component's own behavior (`RocPrCurveCharts` returns `null` when its input
doesn't parse), not something this pass had to add. A `model_kind` value
this frontend doesn't recognize (`"unknown"`, for a job whose model_type
is no longer registered) is narrowed to `undefined` via a small helper
(`lib/model-kind.ts`) before reaching `EvaluationSummary`, which already
knows how to fall back to a generic metrics list for that case.

**Dataset Summary Card** (`components/dataset-summary-card.tsx`) — a small,
pure-display component: Dataset Version, Symbol, Timeframe, Dataset Size
(`sample_count`), Feature Count, and Target Column, all read directly off
one `BenchmarkCandidate`. No new backend field beyond the six above; no
client-side derivation.

**Ranking and the Metric Selector** — entirely frontend, using data the
comparison already returns. `MetricSelector` offers every metric name
present on at least one candidate; choosing one re-sorts
`BenchmarkComparisonTable`'s rows by that metric's value and adds a "Rank"
column, direction-aware via the existing `best_by_metric[].higher_is_better`
(no new backend field — the direction was already being sent for the
"best" highlight). Choosing no metric keeps the original `completed_at`
descending order.

**Multi-experiment comparison** — already supported by the original design
(`experiment_ids: list[uuid.UUID]`, no cap beyond
`evaluation_benchmark_max_candidates`); this pass added end-to-end test
coverage (backend and API) comparing four and three experiments
respectively, confirming no hidden two-item assumption existed anywhere in
`compare()` or the comparison table.

**Deep linking** — every comparison row (and the candidate detail dialog)
now links to: the Experiment (`/experiments/{id}`, a route this platform
already serves), the Training Job (`/ml/training?jobId={id}` — `MLTrainingPage`
gained a small, additive `?jobId=` read via `useSearchParams` that opens
that job's existing detail dialog on load, rather than building a second
detail view), and — when recorded — the downloadable Model Artifact
(`model_artifact_url` above, opened directly; `GET .../artifacts/{type}`
already serves the file with a `Content-Disposition: attachment` header via
FastAPI's `FileResponse`, so a plain anchor triggers a save, no client-side
blob handling needed).

**Export architecture** (`lib/benchmark-export.ts`) — a small, explicit
Strategy + Registry of its own, sized for two formats today and designed
for a third:

```ts
export const BENCHMARK_EXPORTERS: Record<BenchmarkExportFormat, BenchmarkExporter> = {
  csv: { label: 'CSV', build: buildBenchmarkCsv },
  json: { label: 'JSON', build: buildBenchmarkJson },
};
```

Each `BenchmarkExporter.build(response)` returns `{ content, mimeType,
extension }` from the **already-fetched** `BenchmarkResponse` — no new
backend endpoint, no re-fetch. `BenchmarkExportMenu` renders one menu item
per registry entry, so a future PDF exporter is one new entry (its `build`
returning a `Blob`-producing result works unchanged with the same
`downloadBlob` call every export on this platform already uses) — no
component change. CSV building reuses this codebase's shared `csvLine`/
`sanitizeFilenamePart` helpers (`src/lib/csv.ts`), the same ones
`features/indicators/lib/export.ts` already uses — no second
escaping/quoting implementation.

**Benchmark History — the one new backend table this pass adds**
(`app/models/evaluation_benchmark_run.py`, migration
`34ade0f119b6_add_evaluation_benchmark_runs_table`). Mirrors
`MLDatasetBuild`'s own "persist the exact request/response, verbatim"
design: every successful `benchmark()` call is recorded — best-effort,
mirroring `MLDatasetService._record_build`'s "never let bookkeeping sink
the primary outcome" precedent (a `try`/`except Exception` around the
persist, logged on failure, the comparison itself still returned) —
storing the `BenchmarkRequest` and full `BenchmarkResponse` as JSON, plus
denormalized `dataset_version`/`target_column`/`candidate_count` columns
for a cheap list view. `EvaluationBenchmarkRunRepository` mirrors
`MLDatasetBuildRepository`'s exact CRUD/search shape. New endpoints:
`GET /evaluation/history` (paginated list, filterable by
`dataset_version`/`target_column`), `GET /evaluation/history/{id}`
(reopen — the exact request and response, unchanged), `DELETE
/evaluation/history/{id}` (removes only the history record; the underlying
`TrainingJob` rows are untouched). The frontend's `BenchmarkHistoryTable` +
a "Reopen" action reload a past comparison's _exact_ persisted response
(no re-query against possibly-since-changed `TrainingJob` rows) into the
same comparison table/summary/charts a live run renders — one rendering
path for both, not two.

**Metric Registry metadata, rendered explicitly.** `GET /evaluation/metrics`
already returned `category`/`higher_is_better`/`requires_probabilities` per
metric; `MetricCatalogPanel` previously only showed the direction (as an
icon) and a Yes/No probabilities column, with category implicit in which
of the two grouped tables a row appeared under. This pass added an explicit
`Category` chip per row and a text label ("Higher is better"/"Lower is
better") alongside the direction arrow — the same data, made legible
without requiring a reader to infer meaning from an icon or a table's
position on the page.

**Testing.** All of the above is covered without touching a single existing
test's expectations: `tests/evaluation/test_service.py` gained cases for
every new `BenchmarkCandidate` field (present when the training job
recorded them, `None`/absent when it didn't), the four/three-experiment
comparison, and Benchmark History's list/get/delete/best-effort-persist
paths (including the `target_column` filter and a simulated persist
failure); `tests/api/test_evaluation_api.py` gained the same at the HTTP
layer, plus a `>2`-experiment end-to-end run. On the frontend, every new
component (`DatasetSummaryCard`, `CandidateDetailDialog`, `MetricSelector`,
`BenchmarkExportMenu` + `lib/benchmark-export.ts`, `BenchmarkHistoryTable`)
has its own test file, `BenchmarkComparisonTable`'s tests gained ranking
and deep-link cases, and `MLTrainingPage` gained a `?jobId=` deep-link
case. 100% backend coverage maintained on `app/evaluation/`,
`app/services/evaluation.py`, `app/repositories/evaluation_benchmark_runs.py`,
and `app/models/evaluation_benchmark_run.py`. See `docs/testing/TESTING.md`/
`services/api/TESTING.md` for the full inventory.

### Feature Store

> Not built. Features are computed on demand and exported; no persisted,
> versioned feature-value store (`DataArchitecture.md` § D6) exists yet.
> The engine above is the computation half of that context; persistence is
> the missing half.

### AI Research

**Partially implemented.** The Experiment Management System above is BC4's
registry slice — recording configuration, dataset version, and outcomes.
Everything else BC4 owns (`docs/architecture/DomainModel.md` § BC4:
managing experiment _training_ itself, evaluating models, the model
registry) remains not built — this system records the _intent and result_
of a training run; it does not run one. See `AI.md` § "Experiment
Management" for the current, honest boundary between the two.

### Prediction Service

> To be completed in future tasks.

### Portfolio Management

> To be completed in future tasks.

### Risk Engine

> To be completed in future tasks.

### Order Management

> To be completed in future tasks.

### Exchange Integration

> To be completed in future tasks.

### Monitoring

> To be completed in future tasks.

## Data Flow

> To be completed in future tasks.

## External Systems

> To be completed in future tasks.

## Security Boundaries

> To be completed in future tasks.

## Deployment View

> To be completed in future tasks.

## Scalability Strategy

> To be completed in future tasks.

## Reliability Strategy

> To be completed in future tasks.

## Future Expansion

> To be completed in future tasks.

## References

> To be completed in future tasks.
