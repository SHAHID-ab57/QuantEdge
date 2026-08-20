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
