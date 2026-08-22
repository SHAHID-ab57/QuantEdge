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
and the Order Book viewer (`src/features/order-book/`) that renders live
depth tables and a spread summary over the same gateway's reconstructed
order-book messages. It talks to `services/api` over the read-only REST surface described
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
