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
└── builtin/      Auto-discovered indicator modules (sma, ema, rsi)
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
   `SeriesSpec`s), and implement `calculate`.
3. Decorate the class with `@register`.
4. Override `warmup(params)` if the indicator needs N candles before its
   first value.

That is the entire list. It appears in `GET /api/v1/indicators`
immediately, and the dashboard's `/indicators` page renders a correct,
constrained parameter form for it with no frontend work — because the form
is generated from the published specs.

Three reference indicators ship, chosen to cover the three distinct shapes
the contract must support so a fourth has a close precedent to copy: **SMA**
(simple window), **EMA** (recursive/stateful with a defined seed), and
**RSI** (multi-stage, bounded, warmup one longer than its period).

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
