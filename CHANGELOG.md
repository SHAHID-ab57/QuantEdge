# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),

## [Unreleased]

### Added

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
