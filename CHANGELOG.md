# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),

## [Unreleased]

### Added

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
