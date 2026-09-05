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
database session that surrounds it."

**`POST /training-jobs/{id}/run` does not block for the pipeline's
duration.** `TrainingJobService.run` is split into `start` (validate the
job exists and isn't already running, transition it to `running`, log
"Training job started" — all synchronous, committed before the response is
sent) and `execute_run` (run the six-stage pipeline and finalize into
`completed`/`failed`). The endpoint calls `start` inline, then hands
`execute_run` off to `asyncio.create_task()` via
`app/dependencies/training.py`'s `schedule_training_job` — the same
"in-process `asyncio` task, no message broker" pattern
`CandleSyncScheduler` already established for periodic candle sync (see
`app/services/candle_sync.py`), applied here to a one-shot task per run
instead of a persistent loop. `run` itself (`start` + `execute_run` in one
awaited call) is kept as the single entry point every in-process caller
that wants the full outcome synchronously — this suite's own service-level
tests included — still uses.

Calling `/run` again while the job is already `running` is rejected with
409 (`invalid_training_job_transition`, `running -> running` is not a
legal edge in the state machine above), not double-executed — no separate
"is it already running" check exists beyond the state machine itself
already enforcing it.

**The background task opens its own database session.** The request's
session (`get_db`) is closed by the time the scheduled task actually gets a
turn on the event loop, so `run_training_job_in_background` builds a fresh
one from `app.db.engine.get_engine()` — exactly how `CandleSyncScheduler`
opens its own session for each periodic tick, never the request-scoped
instance. `execute_run`'s own `except Exception` still converts a pipeline
failure into a `failed` job with the captured error, same as before; a
second, outer `except Exception` around the whole background task is a
last-resort net for anything that goes wrong _outside_ that call (opening
the session, building the service), so a background task's exception is
never just silently lost the way an unretrieved `asyncio.Task` exception
usually is.

**Shutdown behavior is deliberate, not accidental, and has a disclosed
limitation.** `app/application.py`'s `shutdown()` calls
`cancel_in_flight_training_jobs()` before disposing the database engine —
the same relative ordering `Runtime.shutdown` already uses for
`CandleSyncScheduler.stop()` (stop what uses the engine, then dispose the
engine), generalized from one persistent loop task to a dynamic set of
per-request background tasks tracked in
`app/dependencies/training.py`. Unlike the scheduler's loop, which waits on
an `asyncio.Event` at a safe boundary between ticks, a training run's
background task is cancelled wherever it happens to be — mid-stage,
mid-write. `asyncio.CancelledError` is not an `Exception` subclass, so
neither `execute_run`'s nor the background task's own `except Exception`
catches it: a cancelled task never gets the chance to mark its job
`failed` the normal way. **The real, disclosed consequence**: a training
job whose background task was still running when the app shut down is
left with `status="running"` in the database, and there is no
restart-recovery/watchdog in this platform yet to reconcile it — the same
"no worker/queue service exists yet" limitation this framework has always
carried, not a new one this change introduces. If real distributed or
restart-safe execution becomes necessary later, this is the seam it plugs
into, not something built out now. The same "no alerting" gap applies one
level deeper, too: the outer catch-all's own recovery write
(`_mark_job_failed_after_crash`) is itself only best-effort, and can fail
the same way the crash it's recovering from did (e.g. the database is
genuinely unreachable) — when it does, the job is silently left exactly as
the crash found it (most likely `running`), with a log line and nothing
else, not a second, escalated alert.

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
| POST   | `/api/v1/training-jobs/{id}/run`    | Start the pipeline in the background      |
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
itself has no independent push channel. The Run action's mutation resolves
as soon as the job is transitioned to `running` (not once training
finishes), which this polling was already built to observe — no dialog
logic assumed otherwise, so this became non-blocking with no frontend
behavior change beyond the "Running" status legend's own copy.

**Testing.** `tests/training/` covers the state machine (every legal/
illegal transition), the model adapter registry and the placeholder
adapter's determinism, the pipeline (every stage in order, and every
failure mode, with plain async stub hooks — no database), the repository
(CRUD/search/filter/sort/logs), and the service (lifecycle, `start`/
`execute_run`, and the experiment-integration path, including the
best-effort failure path); `tests/training/test_background.py` covers the
background-execution seam specifically (its own DB session opened after
the original would have closed, a pipeline failure and a crash outside the
pipeline both marking the job failed, the deterministic test-wait helper,
and shutdown cancellation); `tests/api/test_training_api.py` covers the
same surface end to end over ASGI, plus the non-blocking response itself
(an artificially slow pipeline proves the request returns well before it
finishes) and a duplicate concurrent run being rejected, not
double-executed; `tests/repository/test_training_postgres.py`
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

### Live Prediction Service

Every previous milestone (data, features, datasets, experiments, training,
evaluation) ends at a saved model artifact and stops there — nothing
downstream of it existed until this one. This is the first piece: given a
**completed** training job with a saved model, compute a fresh feature
vector for a requested market/timeframe, run the model, and return one
prediction, framed honestly — never a bare number presented as fact.

**Package layout** (`app/prediction/`) — framework-light and
database-free, the same discipline `app/evaluation/` holds itself to:

- `base.py` — `PredictionOutcome`, a plain dataclass (`target_column`,
  `horizon`, `as_of`, `predicted_value`, `confidence`,
  `confidence_unavailable_reason`, `probabilities`, `classes`). Nothing
  here touches the database or a model adapter.
- `engine.py` — `PredictionEngine.assemble(...)` turns an already-computed
  `TrainingJobPredictResponse` (see below) plus the experiment's own
  `target_config` into one `PredictionOutcome`: `resolve_horizon` matches
  the resolved `target_column` (e.g. `next_direction_1`) back to its
  configured target's own `horizon` param by name — never by parsing the
  column's numeric suffix, which would silently drift the moment a target
  generator's naming convention did. `confidence` is `max(probabilities)`
  — the predicted class's own probability — set together with
  `probabilities`/`classes` only when the adapter produced any;
  `confidence_unavailable_reason` is set, in the same words the API and
  frontend both show, whenever it did not (every regressor today).
  `default_engine` is the one shared, stateless instance every request
  uses.
- `registry.py` — not a new Strategy+Registry pattern: reconstructing a
  feature vector has exactly one way to do it (drive the Feature
  Engineering Engine with the experiment's own recorded `feature_set`), so
  this module's only export, `get_model_adapter_registry()`, is a named
  seam onto the Training Framework's **existing** `ModelAdapterRegistry`
  — resolving a job's `model_type` to its `model_kind`, the same way
  `EvaluationService.benchmark` already does for a benchmark candidate.
- `errors.py` — `LiveFeatureReconstructionNotSupportedError` (409 — a job
  completed without training on real data, e.g. `placeholder`, so it
  recorded no `feature_columns`/`target_column` to reconstruct from),
  `TrainingFeatureSetMismatchError` (409 — the experiment's `feature_set`
  was edited, via `ExperimentConfigDialog`, after this job trained, so a
  column the model expects no longer exists), `PredictionRunNotFoundError`
  (404), `InvalidPredictionSortError` (400). Every other failure reuses an
  existing named error rather than duplicating it: a job that isn't
  completed or has no artifact
  (`app.training.errors.PredictionNotAvailableError`, raised by
  `TrainingJobService.predict` itself), an unknown market
  (`app.services.market_query.MarketNotFoundError`), or too little candle
  history for the requested features' warmup
  (`app.features.errors.EmptyDatasetError`, raised by
  `FeatureDatasetBuilder.build` itself).

**Feature reconstruction — the part most likely to silently produce
garbage if done casually.** `app/services/prediction.py`'s
`PredictionService.run` is the one place this actually happens, composing
three already-existing services directly rather than a second copy of any
of them:

1. `TrainingJobService.get` resolves the job and reads its recorded
   `result_summary["feature_columns"]`/`["target_column"]` — the
   authoritative record of exactly what a completed run actually trained
   on (`report["feature_columns"] = list(dataset.feature_columns)`,
   already written by both baseline adapters) — never re-derived here.
2. `ExperimentService.get` reads the linked experiment's own recorded
   `feature_set` — the same field `ExperimentConfigDialog` makes editable
   and `TrainingJobService`'s own `_make_load_dataset_hook` already reads
   for training.
3. `FeatureService.build_raw` — "the one dataset-building path every
   consumer shares" (its own docstring names "a live inference path" as a
   future consumer, written before this milestone existed) —
   recomputes the _same_ features over fresh candles, bounded to a
   `[start, end)` window that ends exactly at the requested `as_of` (or,
   by default, the market's real latest candle, resolved via
   `CandleRepository.get_latest_candle`) and starts far enough back to
   cover the largest feature's own warmup plus a small buffer. The last
   row of that freshly-built dataset — never assumed to be row `0` or
   capped from the wrong end — is the live feature vector; its own
   timestamp (a real, stored candle's `open_time`, never interpolated) is
   the response's `as_of`.
4. **Normalization was investigated, not assumed.** Fitted
   `NormalizationStats` (`app/training/normalization.py`) are already
   persisted onto a completed job's `result_summary["normalization"]`/
   `["normalization_method"]` — closed as part of the normalization
   milestone itself, not this one. `TrainingJobService.predict` already
   reconstructs them and applies the identical transform training used
   (`_normalize_prediction_rows`) before calling the model — this service
   calls that method directly rather than touching a `NormalizationStats`
   or the adapter's artifact itself, so it is structurally impossible for
   this path to fit fresh statistics from the single inference-time row
   (a degenerate, meaningless transform: a single row's own z-score
   against itself is always exactly zero, regardless of its real values).
5. The model runs through the existing, unchanged
   `TrainingJobService.predict(job_id, [row])` — the same method
   `POST /training-jobs/{id}/predict` already calls, so `predict_proba`
   (today: `logistic_regression` only) is never reimplemented, only reused.

**Persistence** — one new table, `predictions` (migration
`20260901_35fe2827d1fb`): `training_job_id`/`experiment_id` (both real
foreign keys, the latter denormalized for cheap filtering — the same
choice `TrainingJob.dataset_version` already made relative to its own
parent), `symbol`, `timeframe`, `target_column`, `horizon`, `as_of`,
`predicted_value` (JSON — a class label or a number), `confidence`
(nullable — not every model produces one), `probabilities`/`classes`
(verbatim, small by construction), `feature_columns`, `model_type`/
`model_kind`, and **`actual_outcome`, deliberately always `NULL`** — no
grading task exists yet (a separate, later milestone item), reserved now
so that task never needs a migration of its own.

**API** — `POST /predictions/run` (runs synchronously — inference on a
single reconstructed row is fast; the known need for a worker/queue
applies to _training_, not this), `GET /predictions/{id}`,
`GET /predictions` (filterable by `training_job_id`/`experiment_id`/
`symbol`, the same pagination convention as `/experiments` and
`/training-jobs`) — see `API.md` § "Live Prediction Service" for the full
request/response shapes and error codes. The response never presents a
prediction as certain: `target_column`, `horizon`, `as_of`, and
`confidence` (explicitly `null` with `confidence_unavailable_reason` when
absent) always accompany `predicted_value`.

**Frontend** (`apps/dashboard/src/features/ml-predict/`, `/ml/predict` —
full detail in `FRONTEND.md` § "Live Prediction Service"): a form (training
job — filtered to completed jobs, symbol, optional as-of timestamp) reusing
the same searchable-combobox pattern `CreateTrainingJobDialog` already
uses; a result panel leading with target and horizon, then the predicted
value, then confidence framed explicitly as a probability (or a plainly
stated reason it isn't available); a Prediction History table mirroring
`benchmark-history-table.tsx`'s exact shape (list, reopen, most-recent
first); and deep links to the source Experiment/Training Job matching the
convention `BenchmarkComparisonTable` already established.

**Testing.** `tests/prediction/test_engine.py` covers `resolve_horizon`
and `assemble` in isolation (classifier vs. regressor shape, an
adversarial case proving `confidence` is the predicted class's own
probability, not just the first or last entry in the row).
`tests/prediction/test_service.py` reuses `tests/training/test_service.py`'s
own real-candle/real-experiment fixtures end to end: feature-vector
reconstruction checked against the real stored latest candle, classifier
and regressor shape, persistence/reopen, Prediction History filtering, and
a dedicated adversarial normalization test (predicting at two different
`as_of` times on the same `normalize_features=True` job must **not**
produce identical probabilities — the one observable symptom a degenerate
single-row normalization bug would produce). `tests/api/test_prediction_api.py`
adds the same at the HTTP layer, including a job that hasn't completed yet
and a job with no real `feature_columns` (`placeholder`). On the frontend,
`PredictionForm`/`PredictionResultPanel`/`PredictionHistoryTable` each have
their own test file, plus a page-level test covering the run → result →
history-reopen flow end to end.

### Prediction Grading

Every previous milestone stopped at a live prediction, persisted honestly
(target, horizon, confidence — never a bare number). This is the next
step: once a prediction's target horizon has actually arrived, determine
what really happened and record whether the prediction was right.

**Verified before writing any code — the open risk flagged when the
Live Prediction Service was first built.** That milestone's own docs asked
whether a live inference's feature vector/normalization was genuinely
consistent with the training job's own recorded statistics; this had not
been confirmed since. It now has: two real, previously-persisted
predictions (`training_job_id=8a948fba…`, `logistic_regression` on
ETHUSD/1h) were pulled from the actual dev database, their raw feature
vectors reconstructed with the real `FeatureService`, normalized with the
job's own recorded `NormalizationStats` via the real `apply_normalization`,
and run through the real persisted model artifact — both reproduced their
stored `predicted_value`/`confidence` **bit-for-bit exactly**, confirming
the live-inference path genuinely uses the training job's own statistics,
not something ad hoc or drifted. The same pass surfaced a real, separate
finding worth recording: that job's `volume` feature at inference time
(the real current market, ~1.5–1.9M) sat millions of standard deviations
outside the training window's own recorded range (`min=0, max=1` — an
early-2024, low-liquidity slice), almost certainly the reason both
predictions reported a saturated 100% confidence. That is a data/
experiment-design characteristic of that one job — not a defect in the
prediction, normalization, or feature-reconstruction code, which this
check confirms is correct — and grading (below) is unaffected by it:
grading only determines what actually happened, independent of how
trustworthy any one job's confidence is.

**Follow-up: the out-of-range training window's root cause, traced to a
specific job and dataset window, not a bug.** The job is
`training_job_id=8a948fba-8416-4ccb-a020-41628581cd38` /
`experiment_id=565ca966-1437-4f28-b7d9-1d58002e38af` ("ETHUSD 1h config
editor test", `dataset_version="manual-test-1"`) — a manual test/demo
experiment, not a curated research dataset, trained 2026-08-31. Its
default "latest N candles" dataset build resolved to
`2024-02-07T03:00Z .. 2024-02-10T00:00Z` — reconstructed and reproduced
bit-for-bit (`ColumnNormalizer.fit` over the real `MLDatasetService`
output for this exact window matches the job's own recorded stats
character-for-character). That window is ETHUSD's own real, `source=
'delta'`-ingested history (confirmed against `candles.source`, all rows
`'delta'`, batch-ingested `2026-08-27`, never hand-seeded) — a genuinely
real, extremely low-liquidity stretch: every one of its 70 training-split
candles has `open == high == low == close` (no trade moved the price for
70 straight hours) and `volume` of exactly `0` or `1` base-asset unit (67
zeros, 3 ones). **Conclusion: not a bug** — feature computation,
normalization fitting, and live-inference reconstruction are all verified
correct on this real data; the actual problem is that this one manual-test
job happened to train on an unrepresentative, near-degenerate historical
slice rather than a recent, liquid window, so its learned "volume" scale
has no relationship to current ETHUSD volume. **Recommendation, not
implemented here**: whether to flag a prediction as low-confidence/
out-of-distribution when a live feature falls far outside its training
job's own recorded min/max is a genuinely separate feature (needs its own
design: which features to check, a threshold, whether to block or just
warn) — a candidate for its own task, not folded into grading.

**Package layout** (`app/prediction/grading.py`) — framework-light and
database-free, mirroring `app/prediction/engine.py`'s own posture:

- `grade_one(...)` turns an already-fetched candle window plus the target
  generator that produced the training label into a `GradingOutcome`
  (`actual_outcome`, `is_correct`, `error`). It does not fetch candles,
  does not decide whether a prediction is gradeable yet, and does not
  touch the database — `PredictionService.grade_pending` (below) is the
  one place all of that happens.
- **Reuses the exact target-generation logic that produced training
  labels — never a reimplementation.** `app.ml_datasets.pipeline.TargetPipeline`
  (the same instance `MLDatasetBuilder` itself drives, via
  `app.dependencies.ml_datasets.get_target_pipeline()`) is run again over a
  fresh, `horizon + 1`-candle window starting at the prediction's own
  `as_of` — the identical target function, not a hand-rolled "is the
  direction up or down" check. Grading is only meaningful if it uses the
  same definition of "correct" the model was trained against; re-deriving
  that definition here would risk silently drifting from it the moment a
  target generator's own logic changed. Which target generator to re-run
  is resolved the same way a live prediction's own horizon already is:
  `app.prediction.engine.resolve_target_entry` matches the experiment's
  recorded `target_config` by column-name prefix (refactored out of the
  existing `resolve_horizon`, so both read the identical authoritative
  entry rather than each re-deriving it their own way).
- **Reuses the existing `accuracy`/`mae` metrics
  (`app/evaluation/metrics/`) for "correct"/"error" — never a new
  formula.** Grading one prediction is exactly those metrics computed over
  a one-element `(y_true, y_pred)` pair: `AccuracyMetric.compute([actual],
[predicted])` is `1.0`/`0.0` for `is_correct` (classification);
  `MaeMetric.compute([actual], [predicted])` is `abs(actual - predicted)`
  for `error` (regression) — the same `MetricRegistry`
  (`app.evaluation.registry.default_registry`) `EvaluationEngine` itself
  reads from, not a second instance.

**Determining gradeability is a data-availability check, not wall-clock
math.** `PredictionService.grade_pending` (`app/services/prediction.py`)
fetches every prediction with `actual_outcome IS NULL`, and for each:
fetches `horizon + 1` candles starting at its own `as_of` (ascending). If
fewer than that many come back, the target candle hasn't closed and been
ingested yet — the prediction is left untouched, not an error, exactly per
spec. When they do, `grade_one` computes the real outcome and
`PredictionRepository.record_grading` persists it. A prediction whose
experiment's `target_config` no longer has a matching entry (edited via
`ExperimentConfigDialog` since this job trained) is likewise left
untouched — nothing to reliably re-run. One unexpected failure grading a
single prediction is caught, logged, and counted separately (`failed`),
never stopping the rest of the pass — the same per-item failure isolation
`CandleSyncScheduler.run_catch_up` already applies per symbol/timeframe.

**A prediction that fails on every pass (not just "not yet knowable") is
discoverable only through that log line — by design, not by gap.**
Unlike `TrainingJob`, `Prediction` has no `error_message`/`status` column
to persistently mark a row as stuck; adding one is a schema change this
task deliberately did not make. The log line itself (`logger.exception`,
`app.services.prediction`) states the real consequence plainly — the row
"will remain ungraded and be retried on every future grading pass until
this is fixed" — rather than a bare traceback a reader would have to
interpret. It fires on every single pass a row keeps failing, exactly like
the training-job background-crash log
(`app/dependencies/training.py`) states its own consequence ("attempting
to mark it failed") rather than leaving it implied.

**A real bug this feature's own tests caught before it shipped.**
SQLAlchemy's `JSON` column type defaults to `none_as_null=False` — a
Python `None` written to `actual_outcome` was being stored as the _JSON literal_ `null` (a real, non-NULL value at the SQL level), not a SQL
`NULL`. Every grading query filters on `actual_outcome IS NULL`; under the
old (default) behavior it would have matched **nothing, ever** — grading
would have silently never picked up a single prediction, including the
two real ones already in the dev database (confirmed both were affected:
`actual_outcome IS NULL` returned `false` for both before the fix). Fixed
by declaring the column `JSON(none_as_null=True)`
(`app/models/prediction.py`) and, for the two rows already written under
the old behavior, a one-time data-fix `UPDATE` in migration `99d6a6e10268`
itself (not autogenerated — a real, reviewed addition). Verified against
the real dev database: both rows are correctly `NULL` post-migration, and
a subsequent grading pass (via the running dev server's own scheduler,
triggered automatically on reload) graded both — `predicted_value="down"`,
`actual_outcome="down"`, `is_correct=true` for both, live, on real data.

**Periodic execution — mirrors `CandleSyncScheduler` exactly, no new
infrastructure.** `app.services.grading_scheduler.PredictionGradingScheduler`
is a single `asyncio` loop task, its own `get_engine()`-backed database
session per tick (never a request-scoped one), an enable flag
(`prediction_grading_enabled`, default `true`) and interval
(`prediction_grading_interval_seconds`, default 300s) — the same shape
`candle_sync_enabled`/`candle_sync_interval_seconds` already established.
Wired into `Runtime.start`/`shutdown` (`app/runtime.py`) alongside
`CandleSyncScheduler`, stopped before the database engine is disposed on
shutdown. `scripts/grade_predictions.py` is the manual one-off entry point,
matching `scripts/sync_candles.py`'s exact shape (`run_grading_once`,
plain stdout summary, non-zero exit on any failed row). No new queue or
message broker — grading one prediction is fast (a handful of small reads
plus one already-fast `TargetPipeline.run` call), the same reasoning
`PredictionService.run`'s own docstring already gives for live inference
itself.

**API** — `GET /predictions/{id}` and `GET /predictions` now also return
`actual_outcome`, `is_correct`, `error`, `graded_at`, and a computed
`available_after` (the instant grading can next determine the outcome,
`as_of + horizon` candle-intervals — computed server-side so the frontend
never re-derives timeframe-to-duration math itself; `null` once graded).
`actual_outcome IS NULL` remains the one authoritative "still pending"
signal, never inferred from the other three fields.

**Frontend** — no new page, per spec: the existing Prediction History
table (`apps/dashboard/src/features/ml-predict/components/
prediction-history-table.tsx`) gained one "Outcome" column. Pending:
"Awaiting outcome — available after `<timestamp>`", never blank. Graded
classification: the real outcome plus the same Correct/Incorrect glyph
(`CheckCircleIcon`/`CancelIcon`, green/red) `prediction-samples-table.tsx`
already renders for a training job's own validation samples — reused, not
a second differently-styled way of showing the same idea. Graded
regression: the real outcome plus its absolute error.

**Testing.** `tests/prediction/test_grading.py` covers `grade_one` against
real built-in target generators/metrics (not stubs) — correct and
incorrect classification, regression error reusing the exact `mae` metric,
an unknown model kind, an unmatched target column, and that too few
candles propagates `InsufficientTargetDataError` rather than silently
grading wrong. `tests/prediction/test_service.py`'s `TestGradePending`
covers the full DB-backed pass: a gradeable prediction graded correctly,
an ungradeable one left untouched (`attempted` counted, nothing changed),
a regressor graded with an error not a correctness flag, an already-graded
prediction never reprocessed, a `target_config` edited out from under a
pending prediction, and one unexpected per-row failure isolated from the
rest of the pass. `tests/services/test_grading_scheduler.py` covers the
scheduler's own start/stop/tick/loop wiring (100% line coverage), mirroring
`tests/services/test_candle_sync.py`'s own conventions. `tests/api/
test_prediction_api.py`'s `TestGradedResponseShape` proves the HTTP
response reflects both states. `PredictionHistoryTable`'s own test file
covers pending, correct, incorrect, and regression-error rendering.

### Backtesting Engine

Given a trained model and a historical date range, generate a prediction at
each step using only data available as of that point, grade each one
immediately against what's actually stored afterward, and report aggregate
performance. This is the milestone that makes the Live Prediction Service
and Prediction Grading trustworthy as a _system_, not just as two features
that happen to work individually — a backtest that used different logic
than live prediction would test a hypothetical twin of the platform, not
the platform itself.

**Two things mattered more than anything else, both proven by a test, not
asserted in prose:**

- **The live prediction and grading code are reused exactly, unmodified,
  called in a loop.** `app/services/backtest.py`'s `BacktestService
.execute_run` calls `PredictionService.run` — the identical
  `PredictionRunRequest` shape every live `POST /predictions/run` call
  uses — once per planned step, and `PredictionService.grade_now` (new,
  additive; internally calls the _same_ private `_grade_one`
  `grade_pending` already uses) immediately after. Neither method gained a
  `backtest_run_id` parameter or any backtest-specific branch; tagging a
  resulting prediction as backtest-generated is a separate, additive
  `PredictionRepository.tag_backtest_run` write performed _after_ `run` has
  already returned, never threaded through it. `tests/backtest/test_service
.py`'s `TestReusesLivePredictionExactly` proves this directly: a live
  call and a backtest step for the identical job/symbol/`as_of` are run
  independently and their full responses compared field-by-field
  (`predicted_value`, `confidence`, `probabilities`, `classes`,
  `target_column`, `horizon`, `model_kind`) — not merely "close", identical.
- **No look-ahead bias, no data leakage — verified adversarially, not just
  read and trusted.** `PredictionService.run`'s own candle fetch already
  uses a half-open `end=reference_time + interval` (the same convention
  `app.services.market_query.normalize_range`/`FeatureService.build_raw`
  established platform-wide), which structurally excludes any candle
  strictly after the requested `as_of` — walking a `for as_of in
plan.as_of_values` loop and calling `run` unmodified at each one
  _inherits_ that guarantee automatically, rather than needing a second
  mechanism to enforce it. `tests/backtest/test_service.py`'s
  `TestNoLookAhead` proves it adversarially: a live prediction is made at a
  fixed `as_of`, then _every_ candle strictly after that `as_of` is deleted
  from the database, and the identical call is repeated — the response
  (`as_of`, `predicted_value`, `confidence`, `probabilities`) is bit-for-bit
  unchanged, directly demonstrating that later candles were never
  reachable at that step, not merely asserting it from reading the code.

**Package layout** (`app/backtest/`) — framework-light and database-free,
mirroring `app/evaluation/`'s own posture:

- `base.py` — `BacktestStepPlan` (the capped `as_of` list to walk, its
  `effective_end`, whether it was `truncated`, and the honest uncapped
  `requested_steps`) and `GradedPredictionRow` (one step's outcome, shaped
  for aggregation) — pure dataclasses, no ORM, no service.
- `engine.py` — `plan_steps(...)` (the only genuinely new computation: which
  `as_of` values to walk, half-open, capped from the _end_ — the same
  "keep the earliest, cut the tail, report it honestly" direction
  `apps/dashboard/src/features/replay/hooks/use-replay-candles.ts`'s own
  `MAX_REPLAY_CANDLES` already established for this platform's other
  range-capping feature, generalized rather than reinvented differently
  here) and `aggregate(...)` (shapes graded rows into `y_true`/`y_pred`/
  `y_proba` and calls `app.evaluation.engine.default_engine.evaluate` — the
  _exact_ `EvaluationEngine` instance every other metric consumer on this
  platform already reads from, never a second copy of `accuracy`/`mae`/
  etc.). `y_proba` is reconstructed only when _every_ row carries both
  `classes` and `probabilities`; otherwise `None`, letting
  `EvaluationEngine`'s own graceful-skip contract (a skipped `roc_auc`, not
  an error) handle it rather than fabricating a probability row.
- `errors.py` — only what's genuinely new to walking a _range_
  (`InvalidBacktestRangeError`, `InvalidBacktestStepError`,
  `InvalidBacktestSortError`, `BacktestRunNotFoundError`). Every failure
  that can also happen to a single live prediction (unknown/incomplete
  training job, unknown market, too little candle history) already has a
  named error raised by `PredictionService.run`/`grade_now` themselves,
  reused verbatim by the walker — never duplicated here.

**`app/services/backtest.py`'s `BacktestService`** is the one place a
`BacktestRun`/`Prediction` ORM row exists in this feature's own code — it
composes `PredictionService`/`TrainingJobService` directly (never a second
copy of either), the same reuse `PredictionService` itself already
established relative to `TrainingJobService`/`FeatureService`. `start()`
resolves the job, its timeframe, and the requested (or defaulted) step,
calls `plan_steps`, persists a `pending` `BacktestRun` row, and atomically
transitions it to `running` — all before returning, so
`POST /backtests/run` reflects `running` immediately. It deliberately does
**not** pre-validate that the job is completed with a saved artifact the
way `PredictionService.run` itself does; duplicating that check would be a
second copy of it. If the job can't actually predict, the very first step
inside `execute_run` raises exactly the error `PredictionService.run`
already raises, and the whole run is finalized `failed` with that message —
one try/except around the entire walk, mirroring
`TrainingJobService.execute_run`'s own shape exactly (not a per-step
isolate-and-continue, which belongs to `PredictionService.grade_pending`
isolating many independent predictions from one bad row — a backtest is
one run, and a step that can't predict at all means the whole run failed,
not that it silently ran shorter than requested).

**Runs asynchronously, reusing the exact same mechanism the training-job
fix already built — not a second one.** The generic fire-and-forget
tracking primitives (`track`/`schedule`/`cancel_all`/`wait_for_all`, one
shared `set[asyncio.Task]`) were extracted out of
`app/dependencies/training.py` into `app/services/background_tasks.py`
once this feature needed the identical mechanism for
`POST /backtests/run`; `app/dependencies/training.py` now delegates to it
under its original public names (zero test breakage), and
`app/application.py`'s `shutdown()` calls the now-generic `cancel_all()`
directly — cancelling an in-flight training run _and_ an in-flight
backtest alike, one shared registry, one shutdown path.
`app/dependencies/backtest.py`'s `run_backtest_in_background`/
`schedule_backtest_run`/`_mark_run_failed_after_crash` mirror
`app/dependencies/training.py`'s own identically-named functions exactly,
including the same disclosed limitation: a backtest whose background task
was still running at shutdown time is left however the crash found it
(most likely `'running'`), with only a log line — no restart-recovery/
watchdog exists yet, the same limitation training jobs already carry.

**Persistence** — a new `backtest_runs` table (migration `2f9216bd92c0`):
training job id, (denormalized) experiment id, symbol/timeframe/step,
`requested_start`/`requested_end`/`effective_end`/`truncated`, lifecycle
`status` (`pending`/`running`/`completed`/`failed`, a `CheckConstraint`
mirroring `TrainingJob`'s own), `error_message`/`started_at`/
`completed_at`, `total_steps`/`completed_steps`/`graded_count`,
`model_kind` (resolved from the model adapter registry, the same way a
live prediction's own is), and `aggregate_metrics` (the exact
`EvaluationReport.metrics` shape, stored verbatim once the run reaches a
terminal status). `BacktestRunRepository.try_transition_to_running` mirrors
`TrainingJobRepository`'s own atomic `UPDATE ... WHERE status = 'pending'`
guard exactly — kept for consistency even though a backtest run's own row
can never actually be raced the way a training job's can (each
`POST /backtests/run` call creates a brand-new row; nothing else can ever
call this on it concurrently).

**This is deliberately _not_ the same fix as the training-job duplicate-run
race, because there is no analogous race to close.** The training-job race
existed because `POST /training-jobs/{id}/run` acts on one _existing,
shared_ job id that two overlapping requests can both name — the fix was
closing a check-then-act gap on that one shared row.
`POST /backtests/run` never takes an existing id at all: every call
creates its own brand-new row, so two concurrent calls (even with
byte-identical parameters) are exactly as independent as two concurrent
`POST /predictions/run` calls for the same job/symbol — both legitimate,
neither contends with the other. `tests/backtest/test_service.py`'s
`TestConcurrentStart` proves this two ways: two genuinely concurrent
(`asyncio.gather`) `start()` calls with identical parameters both succeed,
each getting its own id and its own `running` row (not one winner/one
409); and, separately, `try_transition_to_running` itself is proven
race-safe in isolation — two concurrent transition attempts against one
pre-existing `pending` row (constructed directly, bypassing `start()`) still
leave exactly one winner, the same kind of test training's own fix used,
confirming the mirrored guard genuinely holds even though nothing in this
feature's real call graph ever exercises it that way.

**Grading in backtest mode reads only the exact `horizon + 1` candles for
its own step — a separate property from, and a separate query than, the
no-look-ahead guarantee above.** `PredictionService.grade_now` (reused by
`BacktestService.execute_run`) calls the same private `_grade_one`
`grade_pending` already uses, whose own candle fetch
(`CandleRepository.get_candles(..., start=prediction.as_of, end=None,
limit=prediction.horizon + 1, ...)`) is bounded by the SQL `LIMIT` clause
itself, not a client-side truncation of a wider read — structurally
incapable of returning a row past position `horizon`, regardless of how
much real data exists further in the future. `tests/backtest/test_service
.py`'s `TestGradingBoundary` proves this directly (not merely read and
trusted) with a `CandleRepository.get_candles` spy: against a real
80-candle seeded series, grading a prediction at hour 40 with horizon 1
reads exactly 2 rows (hours 40 and 41), captured via the spy's own
recorded `limit`/`end` arguments and the exact candles returned — the
~38 real candles stored beyond hour 41 are never reached.

**Backtest-generated predictions are tagged distinctly from live ones, so
they never flood the live Prediction History view.** `predictions` gained
a nullable, indexed `backtest_run_id` FK column — `NULL` for every ordinary
`POST /predictions/run` call, set only by
`PredictionRepository.tag_backtest_run` immediately after a backtest step's
`PredictionService.run` call already persisted the row. `PredictionRepository
.search`'s default behavior (no `backtest_run_id` filter given) now
explicitly excludes any tagged row — Prediction History looks exactly as it
did before this column existed; passing a specific `backtest_run_id` shows
_only_ that run's own predictions instead, the Backtest Result view's own
drill-down, reusing the _same_ list endpoint/table, never a second
"backtest predictions" view. `tests/backtest/test_service.py`'s
`TestTaggingAndAggregation` proves both halves of this directly.

**Large ranges are capped, and truncation is reported honestly rather than
silently running a shorter backtest than requested.** `MAX_BACKTEST_STEPS`
(`app/core/config.py`, default `2000`) bounds `plan_steps`; a request
needing more steps is capped from the _end_, keeping the earliest portion
of the range — `BacktestRun.truncated`/`effective_end` (and the API's own
`total_steps` vs. the client's originally-requested range) let a caller see
exactly what actually ran, never a silently-shortened result presented as
if it were the full request.

**A range that reaches past the symbol's latest actually-stored candle is
rejected outright at request time (`BacktestRangeExceedsAvailableDataError`,
400), not silently truncated or run** — unlike the step cap above,
letting it through would mean `PredictionService.run` (never
interpolating) resolves every step past that point to the same last real
candle, collapsing them into repeated, identical predictions that a
completed run's own `aggregate_metrics` would otherwise present as an
ordinary result.

**API**, mirroring the existing Benchmark pattern but asynchronous like
training jobs: `POST /backtests/run` (plans, persists, starts, and returns
immediately — the walk executes in a background task, not before the
response), `GET /backtests/{id}`, `GET /backtests` (list, most recent
first, filterable by training job/experiment/symbol/status). `GET
/predictions` gained an optional `backtest_run_id` query parameter (see
tagging, above) — no new prediction endpoint.

**Frontend** — a new page, `/ml/backtest`
(`apps/dashboard/src/features/ml-backtest/`), continuing the `/ml/training`,
`/ml/evaluation`, `/ml/predict` route family: a form (job, symbol, date
range, optional step, mirroring `PredictionForm`'s own job/symbol
selection), a result panel showing lifecycle status, honest truncation
reporting, and — once complete — aggregate metrics via `EvaluationSummary`
reused verbatim (`summary={}`, since a backtest's own `aggregate_metrics`
is a flat metrics dict with none of a training job's confusion-matrix/
feature-importance detail, and every one of that component's own
sub-sections already renders nothing when its part of `summary` is absent),
a drill-down into the run's own predictions via the _existing_ Prediction
History table (`usePredictionHistory` gained an optional `enabled` option
so this filtered-by-`backtest_run_id` query can be skipped until a run
actually exists), and a Backtest History list mirroring Benchmark History's
own list/reopen shape (no delete action — no `DELETE /backtests/{id}`
exists). Reopening a backtest step's own prediction from the drill-down
reuses `usePrediction`/`PredictionResultPanel` verbatim — the exact hook and
component the Live Prediction page itself uses — rather than a second
"show one prediction" view.

**Testing.** `tests/backtest/test_engine.py` covers `plan_steps` (even
division, end-truncation and its honest `requested_steps`, a partial final
step still counted whole, an empty/backwards range rejected) and
`aggregate` (a hand-computed classification accuracy and regression MAE
against a small fixture set — not re-derived from the engine itself —
`roc_auc` skipped gracefully when any row lacks probabilities, computed
when every row has them, and an empty row set producing an empty report
rather than an error). `tests/backtest/test_service.py` covers both of this
feature's own defining properties (above), tagging/exclusion, aggregate
metrics for both a classifier and a regressor, honest capping/truncation, a
mid-walk failure finalizing the _whole_ run as failed with its own partial
progress recorded, and every named domain error.
`tests/backtest/test_background.py` mirrors
`tests/training/test_background.py` exactly for the shared background-task
seam (own DB session, a crash outside `execute_run` still marked failed, a
failure in the crash-recovery write itself leaving the run `running`, and
deterministic scheduling/cancellation via the shared registry).
`tests/api/test_backtest_api.py` proves the run endpoint returns before the
background walk completes (an artificially slow `PredictionService.run`
must not delay the response), honest truncation reporting over HTTP, and
the Prediction History drill-down end-to-end. Frontend:
`ml-backtest-page.test.tsx` (run/error/truncation/reopen-and-drill-down) and
`backtest-history-table.test.tsx`.

This is the last piece of Milestone 2 (Prediction & Backtesting, per
`TASKBOOK.md`/`ROADMAP.md`) — with the Live Prediction Service, Prediction
Grading, and now the Backtesting Engine all real, tested, and wired in,
Milestone 2 is complete.

**Two items from Milestone 2 were left to verify before Milestone 3 began,
and both were re-confirmed here, against real data, before any new code
was written:**

1. **No-look-ahead.** The automated adversarial proof
   (`tests/backtest/test_service.py::TestNoLookAhead`) was re-run fresh and
   still passes: every candle strictly after a fixed `as_of` is deleted
   from the database, and the identical `PredictionService.run` call is
   repeated — the response is bit-for-bit unchanged. A second, live
   attempt was also made directly against the real dev Postgres database
   (temporarily overwriting three real future ETHUSD candles with extreme
   values, having first backed up their real values, meaning to restore
   them immediately afterward) — Claude Code's own auto-mode safety
   classifier blocked that write before it executed, and it was not
   retried or routed around; the real candles were confirmed unchanged
   afterward. The automated test above is the property's actual proof;
   the live attempt was an additional, ultimately unneeded confirmation.
2. **The training-job endpoint genuinely returns without blocking.** A
   real training job was created against the real dev database
   (`training_job_id=c406b242-8918-463b-8567-6f2b11ba3300`, ETHUSD/1h/
   `logistic_regression`, on the existing `565ca966…` experiment) and its
   `POST /training-jobs/{id}/run` was triggered for real, timed with
   `curl -w '%{time_total}'`: **0.028s**, returning `status: "running"` —
   not `"completed"` — with the background pipeline finishing
   independently moments later (confirmed by polling). This is the same
   real dev database and real code path `ARCHITECTURE.md` § "Machine
   Learning Training Framework" already documents; this pass re-confirmed
   it live rather than re-trusting the existing automated test alone.

### Paper Trading

A virtual trading account: place simulated market orders against real
prices, track positions, and compute PnL. Milestone 3 (Paper Trading &
Risk) — deliberately narrow in scope throughout: long-only, market
orders only, no margin, no shorting, no leverage. Its one automated
order path (see "Automated Strategy" below) is opt-in, off by default,
and reuses this same order-placement machinery rather than a second one
— everything else about "no automation" still holds: there is still no
margin, no shorting, no leverage, and still nothing here that touches
live trading (see Milestone 6's own gate, unaffected by any of this).

**Realistic execution is the one thing this feature exists to guarantee.**
A market order never fills at a perfect, cost-free price — that would be
the paper-trading equivalent of look-ahead bias: an unrealistically
generous simulation is worse than no simulation, because it looks like
evidence. Every fill applies a modeled slippage and fee; neither is ever
skipped, and both are always reported on the resulting order, never
folded silently into one opaque price. `tests/paper_trading/test_pricing.py`
and `tests/paper_trading/test_service.py` prove this with exact numbers
(a buy at a $1000 quote with 5bps slippage/10bps fee fills at exactly
$1000.50, `slippage_applied` exactly $0.50, `fee_applied` exactly $10.005)
— never merely asserted. Verified live too: a real `POST .../orders` for
ETHUSD against the real dev database filled 1 unit at raw price
$2510.20 (the latest real stored candle's own close, `market_data_live`
being `false` in this dev environment) at fill price $2511.4551 — exactly
$2510.20 × 1.0005 — with `fee_applied=$2.5114551` exactly matching 10bps
of the resulting notional.

**Pre-trade risk limits — position sizing, exposure, and a drawdown halt.**
Three account-level percentage limits, extended onto `paper_accounts`
(migration `c1e00878df40`): `max_position_size_pct` (default 10%),
`max_exposure_pct` (default 50%), `max_drawdown_pct` (default 20%), plus
the running state that enforces them — `peak_balance` and
`trading_halted`. Every check in `PaperTradingService.place_order`
(`app/services/paper_trading.py`) runs in this order:

1. **Halted** — a halted account rejects every order outright
   (`TradingHaltedError`, 400, `trading_halted`) until an explicit
   `resume_trading` call.
2. **Position sizing** — this order's _resulting_ quantity in its own
   symbol, valued at the _current_ resolved quote, must not exceed
   `max_position_size_pct` of the account's _current_ balance
   (`MaxPositionSizeExceededError`, 400, `max_position_size_exceeded`).
3. **Exposure** — every other open position's _current_ value (the same
   `resolve_current_price` live-price-with-fallback lookup
   `list_positions` already uses — never a second data path, and never
   each position's own stale entry price) plus this order's own resulting
   value must not exceed `max_exposure_pct` of current balance
   (`MaxExposureExceededError`, 400, `max_exposure_exceeded`). Proven with
   a fixture that buys a position cheap and lets the market carry its
   _current_ value far past what its entry cost would ever suggest, then
   shows a separate, otherwise-trivial order gets rejected purely because
   of that revaluation — the check could not have used entry price and
   still produce this result.

After the trade completes (not before, and never blocking the trade that
causes it), drawdown is re-evaluated: `peak_balance` only ever rises
(`max(peak_balance, new_balance)`); if the new balance has fallen more
than `max_drawdown_pct` below the (possibly just-raised) peak,
`trading_halted` is set. This can only ever flip `False → True` here — a
halted account is rejected at step 1 before ever reaching this point
again. **No self-healing**: balance moving back above the threshold on
its own never clears the flag — only `POST .../resume-trading` does, and
that call also resets `peak_balance` to the account's current balance
(without this, an account resumed while still deep in drawdown against
its old, untouched peak would re-halt after its very next order,
regardless of that order's own direction — making "resume" nearly
indistinguishable from "allow exactly one more order"; resetting the
high-water mark to _now_ is what a manual risk override conventionally
means).

**Concurrency — the same atomic-`UPDATE` guard the training-job
duplicate-run race already established, adapted to a bounded
retry-and-recompute loop.** `TrainingJobRepository.try_transition_to_running`
guards a simple state transition with one
`UPDATE ... WHERE status = 'pending'`; this feature's own check-then-act
(read balance/positions → resolve a live price → check
halted/position-size/exposure → compute the new balance/peak/halt state
→ write it) can't be pinned to one fixed column the same way, because its
precondition depends on live prices and every other open position, not
just this row. `PaperAccountRepository.try_apply_trade_effects` guards it
instead with `UPDATE ... WHERE balance = :expected AND trading_halted =
:expected`: two concurrent orders against the same account can never both
still match an unmodified row (Postgres serializes the two `UPDATE`s on
the same primary key), so the loser's `UPDATE` matches zero rows.
`PaperTradingService.place_order` treats that as "re-read the account and
every open position, recompute every check from scratch, and retry" (up
to `paper_trading_max_order_attempts`, default 5) — never as "proceed
anyway." The loser is re-evaluated against the winner's already-committed
effect, not the stale numbers it started with, so two orders that would
jointly breach a limit can never both succeed. Verified empirically, not
just asserted sequentially:
`tests/paper_trading/test_service.py::TestConcurrentExposureRace` places
two orders for two different symbols via real, genuine
`asyncio.gather` concurrency (two independent `PaperTradingService`
instances, each its own session — the identical shape
`tests/training/test_service.py::test_two_genuinely_concurrent_starts_reject_exactly_one`
already proved for the training-job race), each individually well under
the exposure limit, jointly well over it — exactly one succeeds, the
other is rejected with `MaxExposureExceededError` (not some other,
accidental failure mode), and the database agrees only one position was
ever created. Stable across repeated runs, not a one-off pass.

**The slippage/fee model, documented plainly** (`app/paper_trading/pricing.py`):
a simple fixed-basis-point model, per this feature's own spec — no
order-book depth, no liquidity curve, no venue-specific fee tier.
`paper_trading_slippage_bps` (default 5) moves the fill price _against_
the trader off the resolved quote — a buy fills higher, a sell fills
lower, never in the trader's favor; `paper_trading_fee_bps` (default 10)
charges that many basis points of the fill's own notional
(`fill_price × quantity`) as a fee, always a cost, both settings in
`app/core/config.py`, not hardcoded, so a test can assert the _exact_
modeled amount.

**Price resolution reuses the same real market data every other live
feature already reads from — never a second data path.**
`resolve_current_price` (`app/paper_trading/pricing.py`) reads
`MarketStateManager.get_latest_ticker`/`get_latest_trade` — the identical
live state the browser-facing `/api/v1/ws/market` gateway reads from,
via `app/runtime.py`'s process-wide singleton — when live data is
flowing, falling back to the latest stored candle's own close at the
_finest_ timeframe actually stored for that symbol (`resolution_duration`,
reused from `app/services/candle_ingest.py`, not re-derived) when it
isn't. Every quote's own `observed_at` (a live event's `event_time`, or
the fallback candle's own `open_time`) is compared against
`paper_trading_stale_price_threshold_seconds` (default 300s) and the
fill is marked `is_stale_price=true` if it's older — a fill priced off a
stale fallback candle is never presented as if it used a live, current
price. In this dev environment specifically (`market_data_live=false`),
every fill so far has genuinely used the `candle_close` fallback — the
real, unstaged behavior this feature will actually run under until live
market data is enabled.

**Long-only accounting, stated plainly** (`app/services/paper_trading.py`):
`average_entry_price` (on the materialized `PaperPosition`) is the VWAP of
_fill_ prices only — fees are never blended into cost basis. A **buy**
immediately realizes its own fee as a certain, already-paid cost
(`realized_pnl -= fee_applied`); it does not otherwise realize any
gain/loss — converting cash into a position at cost is not a gain or a
loss until sold. A **sell** realizes
`(fill_price - average_entry_price) * quantity - fee_applied` — the
price-move gain/loss on the quantity actually sold, net of that trade's
own fee; `average_entry_price` itself never changes on a sell. Once every
position an account has ever held is fully closed, `balance` exactly
equals `starting_balance + realized_pnl` — every dollar has either been
spent-then-recovered through a sell or never spent at all.
`unrealized_pnl` is never stored; it's computed fresh on every read,
marked to the _same_ price-lookup path a fill would use (never a
slippage-adjusted hypothetical exit).

**A buy that would take the account's cash balance negative, or a sell
that would exceed the account's currently-held quantity, is rejected
outright** — `InsufficientBalanceError`/`InsufficientPositionError` (both
400), never a partial fill and never a negative balance or a short
position. No margin, no leverage, no shorting exists anywhere in this
feature to make either possible in the first place.

**Persistence** — three new tables (migration `7a3254fe72af`), extended
once (migration `c1e00878df40`) with the risk-limit columns above:
`paper_accounts` (cash `balance`, cumulative `realized_pnl`,
`max_position_size_pct`/`max_exposure_pct`/`max_drawdown_pct`,
`peak_balance`, `trading_halted`),
`paper_orders` (every filled order — `raw_price`, `fill_price`,
`price_source`, `price_observed_at`, `is_stale_price`,
`slippage_applied`, `fee_applied`, `notional`, and `realized_pnl` — set
only for a sell, `NULL` for a buy), and `paper_positions` —
**materialized, not recomputed from order history on every read**, the
same "store the whole answer" precedent `Prediction`/
`EvaluationBenchmarkRun` already established, updated in place by every
buy/sell against that symbol (a fully-closed position is left at
`quantity = 0` rather than deleted, so re-buying later doesn't need to
reinvent an identity — "open positions" queries simply filter to
`quantity > 0`).

**API**: `POST /paper-trading/accounts` (create), `GET .../accounts`
(list, most recently created first — there is no authentication anywhere
on this platform, so this list, plus `GET .../accounts/{id}`, are the
recovery path for "which account is mine"), `POST .../accounts/{id}/orders`
(place and fill a market order, immediately), `GET .../accounts/{id}/orders`
(order history), `GET .../accounts/{id}/positions` (open positions, each
marked to a live price), `GET .../accounts/{id}/summary` (balance,
realized PnL, live unrealized PnL, and total equity),
`GET .../accounts/{id}/risk` (current exposure %, drawdown %, distance to
the exposure/drawdown limits, and halted status — position-sizing has no
single account-wide "current" figure of its own, since it's checked per
order against one symbol's own resulting value, so only its threshold is
reported here), `POST .../accounts/{id}/resume-trading` (clear a
drawdown halt and reset `peak_balance` to the current balance).

**Frontend** — a new top-level page, `/paper-trading`
(`apps/dashboard/src/features/paper-trading/`), alongside `/trades` and
`/replay` rather than under `/ml/` (this feature has nothing to do with
a trained model or a prediction — it trades against real prices directly).
Reuses `MarketSelector` (the chart module's own generic, data-driven
market picker) for the order form's symbol field, and `ConfirmActionDialog`
(the same "are you sure" pattern used elsewhere for a consequential
action) so placing an order is never a single accidental click.
`EmptyStateNotice` covers the no-account-yet state. The task's third named
reuse, `ConnectionStatus` (the Live Market Dashboard's own connection
panel), was deliberately **not** reused verbatim: its props are tied to
`useMarketStream`, a live WebSocket hook this page has no other reason to
run, and forcing that wiring in just for a status chip would be
disproportionate machinery for what this page actually needs. In its
place, a small `LiveDataChip` reads the _same_ `/system/status` poll
`live-status.tsx`/the Health page already use (no new data path) for a
page-level "live data or stored-candle fallback" hint; the accurate,
per-fill signal is `price_source`/`is_stale_price`, visible on every row
of the order history table — the thing this feature actually promises to
make visible. "My account" is a `localStorage`-remembered id
(`usePaperTradingAccountStore`, the same deliberately-durable-not-session-
scoped exception `use-favorite-features-store.ts` already established),
since nothing on this platform authenticates a user to key a real account
off of. A `RiskSummaryPanel` (`components/risk-summary-panel.tsx`) shows
exposure and drawdown each as a value against its own limit (a
`LinearProgress` bar, colored `warning` past 80% of the limit and `error`
once actually over it), the account's halted status, and — only while
halted — a "Resume Trading" action behind the same `ConfirmActionDialog`
pattern. Every order rejection (risk-limit or otherwise) surfaces the
backend's own specific `detail` message verbatim in the existing
Place-an-Order error `Alert` — no separate frontend logic needed to make
"which limit, by how much" visible, since `src/lib/api/errors.ts`'s
existing `toApiError` already carries the backend's `detail` through as
`Error.message` for every endpoint on this platform.

**Testing.** `tests/paper_trading/test_pricing.py`: ticker-then-trade-
then-candle-fallback precedence, staleness marking (fresh vs. older than
the threshold), and the slippage/fee model's exact arithmetic (a buy
fills higher, a sell fills lower, by exactly the configured bps; fee
scales exactly with `fee_bps`, independent of `slippage_bps`).
`tests/paper_trading/test_service.py`: a buy/sell fill's exact slippage
and fee, a fallback fill marked as such (fresh and stale), an over-balance
buy and an over-quantity/no-position sell both rejected (the over-quantity
case sells more than a real, non-zero holding — not merely a sell against
nothing), and a hand-computed fixture (`start $100,000; buy 10 @ $1000;
mark-to-market at $1100; sell 10 @ $1100`) matching every realized/
unrealized figure exactly, including the `balance == starting_balance +
realized_pnl` reconciliation once the position is fully closed. A second
fixture, `TestAverageCostBasisAcrossMultipleBuys`, buys the identical
symbol twice at two genuinely different prices (10 @ $1000, then 10 @
$1200) before selling part of the combined position — proving
`average_entry_price` blends to the real quantity-weighted $1100.55
(neither the first buy's $1000.5 nor the most recent buy's $1200.6 alone,
a distinction the single-buy fixture above can't exercise), the partial
sell realizing exactly $987.50325 against that blended basis, and the
remaining position keeping the same blended average afterward (a sell
never moves it). `tests/api/test_paper_trading_api.py` covers the first
fixture's shape at the HTTP layer plus the unversioned mount. Frontend:
`paper-trading-page.test.tsx` (empty state, account creation, placing an
order end to end, a surfaced order error), `order-history-table.test.tsx`,
`positions-table.test.tsx`, and `format-pnl.test.ts` (the shared
sign-before-dollar-sign formatter every PnL figure on this page uses).

**Stop-loss / take-profit — a researcher sets a threshold on an open
position, and it's watched and closed automatically.** Extends
`paper_positions` with `stop_loss_price`/`take_profit_price` (both
nullable, migration `16e4c2531e7d`), settable at order-open time
(`PaperOrderRequest`'s optional fields, buy only — rejected outright on a
sell, since a sell only ever reduces/closes a position and has nothing
left to protect) or afterward via a dedicated
`PATCH /paper-trading/accounts/{id}/positions/{symbol}`.

**Validation, stated plainly** (`PaperTradingService._validate_thresholds`):
for a long position, `stop_loss_price` must sit below the current price
and `take_profit_price` above it — either would trigger the instant it
was set otherwise. Whenever both are present in the final, merged pair,
`stop_loss_price` must also be strictly below `take_profit_price` — each
is independently valid against its own current price at the moment it's
set, but that alone doesn't stop a high stop-loss and a low take-profit
being set at two _different_ times as the price moves between them; the
cross-check closes exactly that gap. The vs-current-price check applies
only to whichever field a given request actually names — an untouched,
already-valid threshold is never re-rejected just because the price has
since moved past it (proven by a fixture: a take-profit set while price
is low, then a stop-loss set later, individually valid against the new
higher price, but rejected once checked against the earlier, untouched
take-profit — `StopLossNotBelowTakeProfitError`). An order that omits
both fields never touches a position's existing thresholds; the
dedicated update endpoint distinguishes an omitted field (unchanged) from
an explicit `null` (cleared) via Pydantic's `model_fields_set`/
`exclude_unset`, the same partial-update idiom `ExperimentService.update`
already established.

**Monitoring reuses the existing event bus — no new polling loop**
(`app/paper_trading/monitor.py`'s `StopLossTakeProfitMonitor`). It
subscribes to the identical two event types
`MarketStateManager.attach` already does (`TickerUpdated`/
`TradeEventReceived`) via the same `bus.subscribe(event_type, handler)`
pattern, so it's fed by data this platform's bus already carries end to
end, never a second market-data path. Deliberately prices every trigger
check and the resulting fill from the _event's own_ price, not a
follow-up read through `MarketStateManager`: `EventBus.publish` schedules
one `asyncio.Task` per subscriber concurrently with no ordering
guarantee between them, so this monitor's own handler and
`MarketStateManager`'s handler for the _same_ event can run in either
order — the event already carries the freshest possible price, so
re-deriving one through a cache that might not yet reflect this exact
event would only be a slower, riskier path to data already in hand.
Opens its own database session per relevant price event
(`get_engine()`-gated exactly like `PredictionGradingScheduler`'s own
pattern — a silent no-op without a configured database, the default in
this test suite), never a request-scoped one, since there is no HTTP
request behind a bus event.

**A triggered close reuses the exact same fill model and atomic
concurrency guard a manual close uses** (`PaperTradingService
.trigger_close`) — `apply_fill_model` and
`PaperAccountRepository.try_apply_trade_effects`, unmodified — with one
deliberate difference: it always closes _whatever is currently held_,
re-read fresh on every retry, never a quantity fixed once, so a
concurrent partial manual sell doesn't leave it trying to close a
stale, too-large number. **A triggered fill uses a wider slippage
allowance than a manual order**
(`paper_trading_triggered_slippage_bps`, default 25bps vs. the manual
default of 5bps) — a triggered exit during a fast price move is not a
perfect fill either, and pretending otherwise would understate exactly
the risk a stop-loss exists to manage. Verified live-shaped, not just
asserted: a take-profit crossed at exactly $1100 (5x wider than the
manual model) fills at exactly $1097.25 (`1100 × (1 − 25/10000)`), never
the manual model's $1099.45.

**Concurrency — the third occurrence of this project's own atomic
check-then-act guard**, after the training-job duplicate-run race and
the exposure-limit race: a triggered auto-close and a genuinely
concurrent manual close of the same position can never both succeed,
because both funnel through the identical
`try_apply_trade_effects` atomic `UPDATE` on the account row. The loser's
retry re-reads the now-emptied position and fails cleanly — the manual
side with `InsufficientPositionError` (surfaced to its caller normally),
the triggered side by finding nothing left to close and quietly
stopping (a background trigger has no caller to report to). Verified
empirically with two real concurrent operations
(`asyncio.gather(bus.drain(), manual_close_task)`, mirroring the exact
shape `tests/training/test_service.py`'s own duplicate-run race test and
`TestConcurrentExposureRace` already established) — exactly one closing
order results, every time, across repeated runs.

**"What if one tick crosses both levels at once," answered.** With
`stop_loss_price < take_profit_price` enforced at set-time (above),
`price <= stop_loss_price` and `price >= take_profit_price` are
mutually exclusive for _every_ price — the ambiguity is closed by
construction, not resolved by an arbitrary runtime tie-break, so it can't
actually arise through the public API. The monitor still keeps a
deterministic check order (stop-loss checked first) as defense-in-depth
against that invariant ever being violated some other way (a direct DB
write, a future bug); treating downside protection as the higher-priority
signal is the more conservative failure mode if a row is ever
inconsistent. Proven directly: a position's thresholds forced into that
otherwise-unreachable state (`stop_loss_price=180`, `take_profit_price=150`)
by writing straight to the row bypasses `_validate_thresholds`
on purpose — a single tick at $160 (satisfying both `160 <= 180` and
`160 >= 150`) closes with `trigger_reason="stop_loss"`, deterministically.
A **gap** — a tick landing far past a threshold rather than exactly on
it — still triggers correctly (`<=`/`>=`, never an exact-match `==`) and
fills at the _current_, post-gap price with the wider triggered-slippage
model applied on top, never at the stale threshold price itself, exactly
like a real stop order during a fast move.

**Known limitation — a silent symbol never triggers.** Being purely
event-driven (no polling loop, by design — see above), a stop-loss/
take-profit on a position in a symbol that simply stops producing
`TickerUpdated`/`TradeEventReceived` events (an illiquid market, a data
gap upstream) is never re-checked and never fires, no matter how long it
sits past its threshold on whatever price was last actually observed —
there is nothing to wake the monitor for that symbol until a new event
arrives. This is disclosed plainly rather than silently assumed away, the
same way the training-job/backtest "still running at shutdown is left
however the crash found it, with only a log line" limitation is.

**Fill pricing, precisely: the triggering event's own price, never a
fresh `resolve_current_price` call.** `PaperTradingService.trigger_close`
receives the monitor's already-resolved `quote` as a parameter and reuses
it, unmodified, on every retry attempt inside its loop — `apply_fill_model
(quote, side="sell", ...)` is the only place that quote is used, and
`resolve_current_price` does not appear anywhere in `trigger_close`'s own
body (it's called only from `place_order` and `_current_price_for_symbol`,
neither of which this method touches). Proven, not merely reasoned about:
`tests/paper_trading/test_monitor.py::TestTriggeredFillPricesFromTheEventNotAFreshResolve`
builds the monitor with its own `MarketStateManager` that is deliberately
never attached to the bus and never fed a single event (and seeds no
candle either) — if `trigger_close` ever called `resolve_current_price`
against it, that call would raise `NoPriceAvailableError` and the trigger
would be silently logged and swallowed, leaving the position open. The
close still succeeds, which is only possible because the fill priced
directly from the event.

**Registered exactly like `MarketStateManager` — always-on, no special
shutdown handling, and verified race-free.** `Runtime.__init__` constructs
`StopLossTakeProfitMonitor` and calls `.attach(self.bus)` unconditionally,
the same line-for-line pattern `self.state_manager = MarketStateManager()
.attach(self.bus)` already uses (see `app/runtime.py`) — both exist purely
in-memory and are cheap to build, so neither is gated behind
`market_data_live` or a database check at construction time (only the
monitor's own per-event handler is `get_engine()`-gated, at call time).
`Runtime.shutdown()` gives neither an individual unsubscribe call; both
are discarded together when `shutdown_runtime()` drops the whole `Runtime`
(and its `EventBus`) once `bus.drain()` returns. Unlike the training-job/
backtest background tasks — which `app/application.py`'s `shutdown()`
forcibly _cancels_ at whatever point they're at — `EventBus.drain()` never
cancels a handler task; it _awaits_ every pending one to completion. And
because `Runtime.shutdown()` closes the Delta WebSocket client (the only
source of new such events) _before_ calling `bus.drain()`, no new trigger
can even be scheduled during the drain — so an in-flight trigger is
guaranteed to finish its own DB work before `app/application.py`'s
`shutdown()` disposes the engine afterward. This is a genuine difference
from the training-job/backtest limitation above, not the same one worn
differently — there is no analogous "left however it was found" risk here.

**API**: `PaperOrderRequest` gains optional `stop_loss_price`/
`take_profit_price` (buy only); `PaperPositionDTO`/`PaperOrderResponse`
gain `stop_loss_price`/`take_profit_price` and `trigger_reason`
(`"stop_loss" | "take_profit" | null`) respectively;
`PATCH /paper-trading/accounts/{id}/positions/{symbol}` sets/updates/
clears a position's thresholds.

**Frontend**: `OrderForm` gains two optional, buy-only fields (hidden and
cleared the instant the side switches to sell); `PositionsTable` gains an
"SL / TP" column and a per-row edit action opening `SetThresholdsDialog`
(seeded from the position's own current values, a blank field saved as
an explicit clear); `OrderHistoryTable` gains a "Trigger" column — a
filled, `warning`-colored "Stop-Loss"/"Take-Profit" chip for a
market-triggered close, a plain outlined "Manual" chip otherwise —
making an auto-closed exit clearly, visibly distinct from an ordinary
order, never the same row.

**Testing.** `tests/paper_trading/test_monitor.py`: a stop-loss and a
take-profit each close the position when crossed;
the triggered fill's exact wider-slippage arithmetic ($1097.25, never
the manual model's $1099.45); the concurrent triggered-vs-manual-close
race (exactly one closing order, every time); the gap-through-both-levels
edge case (stop-loss wins the deterministic tie-break).
`tests/paper_trading/test_service.py`'s `TestStopLossTakeProfitValidation`/
`TestUpdatePositionThresholds`: both vs-current-price rejections, the
cross-validation gap between two different set times, thresholds set at
order-open time, an unrelated later buy never clearing them, and the
dedicated endpoint's set/update/clear/not-found paths.

**Automated Strategy — the platform's one automated order path, opt-in,
off by default, and not a new one.** An account may enable a single
automated strategy: each scheduler tick, request a fresh prediction and,
if its confidence clears a configured threshold, place an order through
the exact same `PaperTradingService.place_order` a manual order already
goes through — the same halted check, the same position-sizing/exposure
checks against live prices, and the same atomic `try_apply_trade_effects`
concurrency guard (its fourth occurrence, after the training-job
duplicate-run race, the exposure-limit race, and the SL/TP
triggered-close race). This does **not** change anything about
Milestone 6 (Paper Trading → live trading readiness): live trading
remains gated on extensive validation regardless of paper-trading
performance, automated or manual — nothing here shortens or bypasses
that gate.

**Per-account config, off by default.** Three new columns on
`paper_accounts` (migration `9a50eaff41a2`): `strategy_enabled` (boolean,
default `false` — a researcher must explicitly opt in; there is no
platform-wide setting that turns it on for existing or new accounts),
`strategy_training_job_id` (nullable FK → `training_jobs.id`, `ON DELETE
SET NULL`), `strategy_confidence_threshold_pct` (default 65%, matching
this platform's existing percentage convention for every other
risk/threshold field on this row — not the raw 0–1 fraction
`PredictionResponse.confidence` itself uses), `strategy_default_stop_loss_pct`
(default 5%, constrained `(0, 100)` — never omittable: there is no way to
enable the strategy without a stop-loss percentage in force).
`PATCH /paper-trading/accounts/{id}/strategy`
(`PaperTradingService.update_strategy_config`) is the one place these
change — the same partial-update idiom (`model_fields_set`)
`update_position_thresholds` already established, validated against the
_final_, merged state: enabling with no `strategy_training_job_id` at all
is rejected (`StrategyMissingTrainingJobError`, 400,
`strategy_missing_training_job`), naming a job that doesn't exist reuses
`app.training.errors.TrainingJobNotFoundError` verbatim (404,
`training_job_not_found` — not duplicated, matching this module's own
"reuse another domain's error rather than invent a second one"
convention), and naming a job with no recorded `symbol` (never trained on
real market data) is rejected too
(`StrategyTrainingJobMissingSymbolError`, 400,
`strategy_training_job_missing_symbol`). Disabling never requires any of
this — an account can always be turned off regardless of its training
job's own state.

**Which market the strategy trades is derived, never separately
configured.** The account names a training job, not a symbol —
`app.services.paper_trading_strategy` reads that job's own recorded
`symbol` (`TrainingJob.symbol`) fresh every cycle and predicts/trades
exactly that market, so a strategy can never be pointed at one job's
model and a different, unrelated symbol.

**The periodic scheduler mirrors `CandleSyncScheduler`/
`PredictionGradingScheduler` exactly** — `PaperTradingStrategyScheduler`
(`app/services/paper_trading_strategy.py`): a single `asyncio` loop task,
its own database session per tick, `run_strategy_tick`/`run_strategy_once`
matching the `run_catch_up`/`run_grading_tick`/`run_sync_once`/
`run_grading_once` naming convention, gated on its own
`paper_trading_strategy_scheduler_enabled` setting (default `true`, 300s
interval) — but that flag only controls whether the _loop_ runs at all.
The real, per-account opt-in is `strategy_enabled` on the database row,
read fresh via `PaperAccountRepository.list_strategy_enabled` at the top
of _every_ tick, never cached — so **disabling an account takes effect by
its very next tick**, proven directly by
`tests/paper_trading/test_strategy_scheduler.py::TestDisablingStopsFutureCycles`:
a tick that opens a position, an explicit disable, and a second tick that
`attempted=0`s the same account entirely (it's simply absent from that
tick's own query) — no new decision is ever logged for it afterward.
Wired into `Runtime.start`/`Runtime.shutdown` identically to the other
two schedulers (`app/runtime.py`).

**The decision, each tick, per enabled account:** request a fresh
prediction (`PredictionService.run`, the exact same live-inference path
`POST /predictions/run` uses) for the job's own symbol; if `confidence`
is unavailable (an unsupported model kind) or below
`strategy_confidence_threshold_pct`, do nothing; otherwise interpret
`predicted_value` — `"up"` is bullish, `"down"` is bearish, anything else
(`"flat"`, a regressor's own number) is not a directional call and does
nothing either. Flat + bullish opens a buy, sized at half the account's
own `max_position_size_pct` of current balance (there is no separate
strategy-specific position-sizing config — this is a deliberately
conservative default, leaving headroom for slippage/fee and any other
open exposure) with a stop-loss attached at
`strategy_default_stop_loss_pct` below the resolved price. Long +
bearish closes the full held quantity. Long + bullish and flat + bearish
are both "already consistent with the signal" — no shorting, ever, for
an automated order exactly as for a manual one.

**Every automated position carries a stop-loss — structurally, not by
convention.** The buy request `place_order` receives always names
`stop_loss_price`; there is no code path that opens an automated position
without one. If the price has moved enough by fill time that the
precomputed stop-loss would no longer be valid,
`place_order`'s own `InvalidStopLossPriceError` is the backstop — caught
generically alongside every other order-placement failure (see below)
and logged as a `no_action` decision, self-healing on the next tick,
never silently opening an unprotected position.
`tests/paper_trading/test_strategy_scheduler.py::TestAutomatedPositionsAlwaysCarryAStopLoss`
proves the resulting position's `stop_loss_price` is set, and matches
the configured percentage below the order's own `raw_price` exactly.

**"Just another caller," proven, not merely asserted.**
`TestSharesExistingRiskLimits::test_a_strategy_order_that_would_breach_max_exposure_is_rejected`
configures a tight `max_exposure_pct`, pre-fills most of that budget with
an ordinary _manual_ buy in a different symbol, and shows the automated
buy is rejected by the identical `MaxExposureExceededError` a manual
order would hit in the same situation — no order placed, no position
opened, one `no_action` decision logged naming the rejection. A halted
account rejects an automated close exactly like a manual one too
(`TestLongAndBearishClosesThePosition
::test_a_rejected_automated_close_is_logged_as_no_action`).

**Every cycle is logged — acted on or not, and why.** A new table,
`paper_strategy_decisions` (migration `9a50eaff41a2`): `account_id`,
`training_job_id`, `symbol`, `action` (`'opened' | 'closed' | 'no_action'`,
check-constrained), `reason` (plain language, always present),
`predicted_value`/`confidence` (both nullable together only when no
prediction was ever obtained this cycle), `confidence_threshold_pct` (a
snapshot of the account's own threshold _at the moment of this cycle_ —
never re-read from a possibly-since-changed account),
`prediction_id`/`order_id` (independently nullable — a logged `no_action`
after a real prediction names the former without the latter). Exactly
one row is written per strategy-enabled account per tick, unconditionally
— proven by
`TestEveryCycleIsLogged::test_every_tick_is_logged_whether_it_acted_or_not`
(three ticks — below-threshold, opens, non-directional signal — three
logged decisions, one of each outcome) and
`TestBelowThresholdResultsInNoOrder` (a below-threshold cycle places no
order but is still logged, reason naming the threshold). `GET
/paper-trading/accounts/{id}/strategy/decisions` is this table's own
paginated read, the Strategy panel's decision log data source.

**API**: `PaperAccountResponse` gains `strategy_enabled`/
`strategy_training_job_id`/`strategy_confidence_threshold_pct`/
`strategy_default_stop_loss_pct`; `PATCH .../strategy`
(`PaperStrategyConfigUpdateRequest`) sets them; `GET .../strategy/decisions`
(`PaperStrategyDecisionListResponse`) lists the decision log.

**Frontend**: a new "Automated Strategy" section on `/paper-trading`,
shown once an account is selected — `StrategyPanel` (enable/disable
switch, default off; a training-job picker restricted to completed jobs;
confidence-threshold/stop-loss fields; an explicit "Paper trading
only — this never places a real trade" disclosure, matching this
platform's own no-real-money framing everywhere else on this page) and
`StrategyDecisionLogTable` (every cycle, most recent first — a filled
"Opened"/"Closed" chip visually distinct from an outlined "No Action"
one, the same "make an automated outcome visibly distinct, never a plain
row" precedent `OrderHistoryTable`'s own "Manual"/"Stop-Loss"/
"Take-Profit" chips already established for a triggered close).

**Every cycle genuinely re-requests a fresh prediction — never a cached
or reused one — proven, not just asserted.** `_process_account` calls
`PredictionService.run(PredictionRunRequest(training_job_id=job_id,
symbol=symbol))` with no `as_of`, every single tick; `PredictionService
.run` always constructs a brand-new `Prediction(...)` and persists it via
`PredictionRepository.create` — an unconditional `INSERT`, never an
upsert or a by-`as_of` lookup — so even two ticks run back-to-back
against the exact same still-latest candle (nothing new has closed yet)
genuinely call the model twice and persist two distinct rows, never
reusing the first. `TestEachCycleRequestsAGenuinelyFreshPrediction`
proves this by counting real calls into a stub across two consecutive
ticks and asserting two distinct prediction ids, never one reused.
**What actually prevents acting twice on that repeated, identical
signal is the ordinary flat/long position-consistency check below, not
any prediction-level deduplication** — a second, freshly-computed "up"
while already long is simply "already consistent," logged `no_action`;
there is no `as_of`/prediction-id dedup anywhere in this path.

**Known limitation — no out-of-distribution or confidence-quality
safeguard.** `confidence_threshold_pct` is compared directly against
`PredictionResponse.confidence` with no other check. The Prediction
Grading section above already documented a real, previously-observed
case where a live feature (`volume`) sitting far outside a job's own
training range produced a saturated, meaningless 100% confidence — that
same failure mode passes through to the strategy identically to a
genuine high-confidence signal; a 65% default threshold would clear it
easily. Whether to flag/block on out-of-range live features was already
recorded there as "a genuinely separate feature... a candidate for its
own task, not folded into grading" — it has not been built here either,
and this is a real gap, not a rounding error: a job known to be
OOD-affected is not treated any differently by the strategy than a
trustworthy one. Disclosed here plainly, the same way the SL/TP
monitor's own silent-symbol limitation is, rather than assumed away.

**Known limitation — the kill switch is a tick-boundary guarantee, not
a mid-tick one.** `strategy_enabled` is read exactly once per tick, at
the top (`list_strategy_enabled`); `_process_account` never re-checks it
afterward, and `place_order` itself has no concept of `strategy_enabled`
at all (only `trading_halted`, a different flag it re-reads fresh on its
own). A disable landing after an account was already selected into a
tick's own batch, but before that account's own order is placed, does
**not** abort the in-flight cycle — the order still completes.
`test_disabling_mid_cycle_does_not_abort_an_already_in_flight_tick`
proves this directly: it disables the account from inside the stubbed
prediction call itself (the exact midpoint of a cycle) and shows the buy
still completes, with the account already showing disabled by the time
the tick returns. "Disabling takes effect before the next cycle" (proven
separately by `TestDisablingStopsFutureCycles`) means exactly that —
_before the next cycle begins_ — never mid-cycle.

**Stop-loss mandatory attachment, precisely.** There is no test of
literal "an automated buy is rejected for lacking a stop-loss," because
there is no code path that could ever attempt one without it —
`_open_position` computes `stop_loss_price` unconditionally and always
includes it in the `PaperOrderRequest` it builds; there is no flag or
branch that omits it. The real question is whether the _percentage_
itself could ever be degenerate (`0` or `NULL`), and that is blocked at
three independent layers, each with its own test:
`PaperStrategyConfigUpdateRequest.default_stop_loss_pct` rejects `0`
(`gt=0`) and, since a fix made during this review, an explicit `null`
too (`_reject_explicit_null_thresholds` — before this fix, `{"default_
stop_loss_pct": null}` parsed successfully, since Pydantic's `gt=0`
does not constrain an explicit `None` on an `Optional` field, and would
have reached `update_strategy_config`'s `Decimal(None)` call, raising an
unhandled `TypeError`/500 instead of a clean 422); and the database's
own `ck_paper_accounts_strategy_default_stop_loss_pct_valid` check
constraint rejects `0` even for a direct ORM write that bypasses the
service and schema entirely (`test_the_database_itself_rejects_a_
zero_stop_loss_even_bypassing_the_service`).

**Position-consistency, all four cases, none a silent fallthrough:**
flat + bullish opens; long + bearish closes; flat + bearish and long +
bullish are both "already consistent" — `no_action`, logged with a reason
naming which ("...no short is ever opened" / "...already long, no
change to make") — each has its own dedicated test in
`TestAllFourPositionConsistencyCases`, not left as an incidental
byproduct of some other scenario.

**Classification-only, in effect — not enforced by an explicit
`model_kind` check.** `update_strategy_config` never inspects a
training job's `model_kind`/`target_column`; a regression job can be
named and enabled without any rejection. In practice it can never act:
per `PredictionResponse`'s own docstring, `confidence` is populated only
for an adapter that supports `predict_proba` ("today:
`logistic_regression`") — always `None` for a regressor — so a
regression job's every cycle is rejected at the mandatory-confidence
gate before signal interpretation is ever reached, proven with a real
trained `linear_regression` job, no mocking
(`TestRegressionJobsCanBeConfiguredButNeverAct`). `_interpret_signal`
itself is a second, defense-in-depth layer regardless — it only ever
matches the literal strings `"up"`/`"down"`, so even a hypothetical
future adapter that did report a confidence for a regressor would still
never have its plain numeric `predicted_value` treated as directional
(`test_interpret_signal_never_matches_a_numeric_value`).

**Testing.** `tests/paper_trading/test_strategy_scheduler.py`: a
confident, above-threshold prediction with a flat position opens a buy;
a below-threshold prediction places no order but is logged; every
automated buy carries a correctly-computed stop-loss; a strategy order
is rejected by the same exposure limit a manual order would hit; a
confident bearish signal while long closes the position (and a halted
account rejects that close, same as a manual one); disabling stops the
very next tick (and does not abort an already in-flight one); every tick
— acted or not — is logged; all four position-consistency cases; a
regression job can be configured but never acts; every cycle is a
genuinely fresh prediction, never cached, with double-acting on a
repeated signal prevented by position-consistency, not dedup; scheduler
start/stop/no-database-configured wiring, mirroring
`tests/services/test_grading_scheduler.py`'s own conventions.
`TestRealPredictionWiring` proves the unstubbed path too — a genuinely
trained job's own recorded symbol, a real `PredictionService.run` call,
one logged decision, no mocking of the prediction pipeline itself.
`tests/paper_trading/test_service.py`'s `TestUpdateStrategyConfig`: the
disabled-by-default starting state, a successful enable against a real
completed job, the three rejection paths (no job named, unknown job, a
job with no recorded symbol), disabling never requiring a job, partial
updates leaving untouched fields alone, a stop-loss of `0` or an explicit
`null` rejected at the schema layer, and the database's own check
constraint as the last-resort backstop against a `0` stop-loss even
bypassing the service.

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

> Built — see § "Live Prediction Service" and § "Prediction Grading" above.
> This heading is kept only so the outline this document has always used
> still lists the bounded context by name; it is not a second, separate
> capability.

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
