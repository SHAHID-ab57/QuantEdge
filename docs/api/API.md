# API

## Purpose

HTTP API of the AI-powered Ethereum Market Analysis Platform, served by the
FastAPI service in `services/api` (OpenAPI docs at `/docs`).

## Status

Draft — v1 surface is read-only and unauthenticated (monitoring + market data).

## Overview

The API exposes historical market data and operational monitoring:

- Liveness and metadata: `GET /health`, `GET /api/v1/health`
- Market data (read-only): `GET /api/v1/markets`, `/api/v1/markets/{symbol}/candles`, ...
- Platform health monitoring: `GET /api/v1/system/health|status|metrics`

## Endpoints

### Liveness

| Method | Path             | Purpose                                    |
| ------ | ---------------- | ------------------------------------------ |
| GET    | `/health`        | Liveness + DB connectivity (503 when down) |
| GET    | `/api/v1/health` | Versioned alias of `/health`               |

### Market data

| Method | Path                                     | Purpose                                                                                                                  |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| GET    | `/api/v1/markets`                        | All tracked markets, ordered by symbol                                                                                   |
| GET    | `/api/v1/markets/{symbol}/timeframes`    | Timeframes with stored candles                                                                                           |
| GET    | `/api/v1/markets/{symbol}/candles`       | Paginated candle history (limit/offset)                                                                                  |
| GET    | `/api/v1/markets/{symbol}/candles/stats` | Aggregate stats for a timeframe/range (count, min/max price, avg volume, first/last candle); 404 when the range is empty |
| GET    | `/api/v1/markets/{symbol}/latest`        | Newest candle for a market/timeframe                                                                                     |

### Technical indicators

| Method | Path                                         | Purpose                                                       |
| ------ | -------------------------------------------- | ------------------------------------------------------------- |
| GET    | `/api/v1/indicators`                         | Catalogue of every registered indicator, with parameter specs |
| GET    | `/api/v1/indicators/{indicator}`             | One indicator's metadata, parameters, and output series       |
| GET    | `/api/v1/markets/{symbol}/indicators/{name}` | Run one indicator over the market's stored candles            |

**The catalogue is the contract.** Each entry publishes every parameter's
type, label, description, default, required-ness, inclusive `minimum`/
`maximum`, and permitted `choices` — enough for a client to build a
complete, correctly-constrained input form without hardcoding anything
about any particular indicator. That is deliberate: registering a new
indicator on the backend must not require a frontend change (the dashboard's
`/indicators` page generates its whole parameter form from this response).

**Calculation parameters are ordinary query parameters.** Beyond the
reserved `timeframe`, `start`, `end`, and `limit`, every query key is
passed to the indicator and validated against its own declared specs:

```http
GET /api/v1/markets/ETHUSD/indicators/sma?timeframe=1h&period=20&source=close
```

An unknown parameter is **rejected, not ignored** — a typo that silently
fell back to a default would return a plausible-looking but wrong series,
the worst failure mode for a research tool.

**Response shape.** `timestamps` holds the candle open times, and every
entry in `series` is aligned index-for-index with it. A `null` value marks
a warmup position where the indicator is not yet defined — never a
calculation failure, which arrives as an error response instead:

```jsonc
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "indicator": { "name": "sma", "label": "Simple Moving Average", "...": "..." },
  "parameters": { "period": 20, "source": "close" }, // fully resolved, defaults applied
  "timestamps": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
  "series": [{ "name": "sma", "label": "SMA(20)", "values": [null, 3055.25] }],
  "meta": {
    "candles_analyzed": 2,
    "warmup_candles": 1,
    "execution_time_ms": 0.08,
    "database_time_ms": 3.2,
    "cache_status": "miss",
    "generated_at": "2026-01-01T02:00:00Z",
  },
}
```

Indicator values serialize as JSON **numbers**, not the decimal-as-string
convention the candle endpoints use. An EMA or RSI is a float
approximation by construction, and a lossless decimal string would imply a
precision the calculation does not have.

Indicator-specific error codes: `indicator_not_found` (404),
`invalid_indicator_parameter` (400), `insufficient_data` (400 — the range
is shorter than the indicator's warmup), and `indicator_execution_failed`
(500 — a bug inside one indicator, named so it is obvious which). The
shared `market_not_found`, `candle_not_found`, `invalid_timeframe`,
`invalid_range`, and `limit_exceeded` codes apply here too.

### Platform health

| Method | Path                     | Purpose                                            |
| ------ | ------------------------ | -------------------------------------------------- |
| GET    | `/api/v1/system/health`  | Per-component status (always 200, states in body)  |
| GET    | `/api/v1/system/status`  | Uptime, version, WS + ingestion freshness          |
| GET    | `/api/v1/system/metrics` | Stored counts, message processing, bus/state stats |

Components reported by `/system/health`: `api`, `database`, `delta_rest`,
`delta_ws`, `event_bus`, `state_manager`. WebSocket status reflects the
**live connection state** (stopped/connecting/connected/disconnected with
subscriptions, message counts, reconnects, heartbeats, and uptime in
`/system/status`), never the configured mode. DB-derived metric fields are
`null` when no database is configured.

### WebSocket (live market stream)

| Method | Path                | Purpose                                                           |
| ------ | ------------------- | ----------------------------------------------------------------- |
| WS     | `/api/v1/ws/market` | Live trade, ticker, and order-book updates for subscribed symbols |

The platform's one server-to-browser push channel — the frontend never
connects to Delta Exchange directly. A client sends
`{"action": "subscribe", "symbols": [...]}` to receive anything (no symbol
is implicit); the server replies with an immediate `snapshot` and then
`trade`/`ticker`/`orderbook` messages as they occur, plus `pong` for a
client `ping`. Order-book messages carry an already-sorted (bids
descending, asks ascending), depth-limited (100 levels/side) _reconstructed_
book — snapshot merged with incremental diffs, not a single raw exchange
message — built by `app/marketdata/orderbook.py`'s `OrderBookAggregator`.
Full wire format is documented at the top of
`app/api/v1/endpoints/market_stream.py`; see `FRONTEND.md` § "Live Market
Dashboard" and § "Live Order Book Viewer" for how the two implemented pages
consume it.

## Authentication

None — the current surface is read-only and public. Private endpoints will
use HMAC/JWT credentials when trading/AI surfaces are added.

## Error Handling

- Domain errors return `4xx` with `{"code": "...", "detail": "..."}`.
- Liveness endpoints return `503` when the database is unreachable.
- System endpoints always return `200`; component states are carried in the
  body so dashboards can render granular states.

## Rate Limiting

Not implemented. Delta REST calls are bounded by the client's retry/backoff
policy (see `app/integrations/delta/client.py`).

## SDKs

None. The dashboard consumes these endpoints directly via axios (see
`apps/dashboard/src/lib/api/`).
