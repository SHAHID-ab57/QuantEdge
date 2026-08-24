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

### Data Collection

> To be completed in future tasks.

### Data Storage

> To be completed in future tasks.

### Feature Store

> To be completed in future tasks.

### AI Research

> To be completed in future tasks.

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
