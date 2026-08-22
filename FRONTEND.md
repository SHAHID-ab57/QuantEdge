# Frontend

## Purpose

Documents the Next.js dashboard in `apps/dashboard`: its stack, routing,
feature-module pattern, API client conventions, and the reusable candlestick
chart module. Read this alongside
[`docs/architecture/EngineeringStandards.md`](docs/architecture/EngineeringStandards.md)
(general coding conventions) and [`docs/api/API.md`](docs/api/API.md) (the
backend surface the frontend consumes).

## Status

Active — `apps/dashboard` implements Health, Markets, History (with a
candlestick chart), Live Market (resolved market selection, real-time
price/chart/trade tape, and an operational connection panel), and Order
Book (live depth tables, spread, and cumulative-depth visualization).
Dashboard, Research, and Settings remain placeholders.

## Stack

Next.js 15 (App Router, typed routes) · React 19 · TypeScript (strict) ·
Material UI v7 (dark-only theme, CSS variables) · TanStack Query (server
state/polling) · Zustand (local UI state) · Axios (API client) · Zod
(runtime validation of every API response) · TradingView lightweight-charts
(candlestick charting) · Vitest + Testing Library (tests).

## Routing

All real pages live under the `(dashboard)` route group
(`src/app/(dashboard)/`), wrapped by `AppShell` (sidebar + top bar,
`src/components/layout/`). `/` redirects to `/dashboard`.

| Route          | Status                                                                  |
| -------------- | ----------------------------------------------------------------------- |
| `/health`      | Implemented — platform/DB/bus/state health, polled REST                 |
| `/markets`     | Implemented — filterable/sortable market table + detail panel           |
| `/history`     | Implemented — historical candle browser, **Chart** and **Table** tabs   |
| `/live-market` | Implemented — real-time price, chart, and trade tape (see below)        |
| `/orderbook`   | Implemented — live depth tables, spread, and depth selector (see below) |
| `/dashboard`   | Placeholder                                                             |
| `/research`    | Placeholder                                                             |
| `/settings`    | Placeholder                                                             |

## Feature module pattern

Each implemented feature lives in `src/features/<name>/`: a
`<name>-page.tsx` client component alongside `components/`, `hooks/`, and
`lib/` subfolders, with tests co-located as `*.test.ts(x)`. Business logic
stays in `src/features/`; shared, cross-feature plumbing lives in
`src/lib/` and
`src/components/`.

## API layer

A single Axios instance (`src/lib/api/client.ts`) talks to `services/api`
at `NEXT_PUBLIC_API_URL`. Every typed fetch function
(`src/lib/api/market.ts`, `system.ts`) immediately validates the response
against a Zod schema (`src/types/api/`) — an API response is never trusted
as typed without also being runtime-checked. New API client functions must
follow this pattern; do not add a second HTTP client or bypass schema
validation.

## Chart module

`src/components/chart/` is a reusable module that renders historical OHLCV
data as a candlestick chart with TradingView's **lightweight-charts** — the
only chart library used in this codebase. It has no dependency on the
History feature and can be dropped into any future page.

### Component hierarchy

```text
ChartContainer                 data fetching, loading/empty/error states
├── ChartToolbar                fit-content button, candle count/truncation note
│   ├── MarketSelector           (only rendered in "standalone" mode)
│   └── TimeframeSelector        (only rendered in "standalone" mode)
├── CandlestickChart            imperative lightweight-charts wrapper (React.memo)
└── ChartLegend                 OHLCV + timestamp readout
```

`data-adapter.ts` (pure functions) and `hooks/use-chart-candles.ts` (data
fetching) sit alongside these components but render nothing themselves.
`chart-theme.ts` derives every lightweight-charts color/option from the
active MUI theme — the chart does not introduce a second theming system.

### Data flow

```mermaid
flowchart LR
    A["GET /api/v1/markets/{symbol}/candles\n(existing endpoint, paginated)"] --> B["useChartCandles\n(hooks/use-chart-candles.ts)"]
    B -->|"paginates dir=desc,\nreverses to ascending,\ncaps at MAX_CHART_CANDLES"| C["Candle[]\n(string OHLCV, ISO timestamps)"]
    C --> D["toChartSeries\n(data-adapter.ts)"]
    D -->|"drops invalid/duplicate points,\nUTCTimestamp seconds,\nnumeric OHLCV"| E["CandlestickData[] + HistogramData[]"]
    E --> F["CandlestickChart\n(lightweight-charts)"]
    F -->|"onCrosshairMove"| G["ChartLegend"]
```

`ChartContainer` **reuses** the existing `services/api` candle endpoint —
it does not call a new or duplicate endpoint. A chart needs the full range
in one shot rather than one UI page at a time, so `useChartCandles`
transparently paginates `GET /markets/{symbol}/candles` (whose backend page
size caps at 1000 — `candles_max_limit` in `services/api/app/core/config.py`)
into as many requests as needed, always requesting newest-first
(`dir=desc`) and reversing the merged result, so a truncated fetch keeps
the _most recent_ candles rather than the oldest.

### Integrating with an existing filter UI (History page)

The History page (`src/features/history/history-page.tsx`) already has a
market/timeframe/date-range form (`HistoryForm`) reused by both its table
and its new **Chart** tab — `ChartContainer` is rendered with
`symbol`/`timeframe`/`start`/`end` taken directly from the page's existing
query state and renders **no selector UI of its own** there
(`ChartToolbar`'s `markets`/`availableTimeframes`/`onSymbolChange`/
`onTimeframeChange` props are simply omitted). This is deliberate: the task
that added this chart required reusing the History explorer's filters
rather than building a second, parallel set. `MarketSelector` and
`TimeframeSelector` still exist and are exported for a future page that
embeds the chart **without** an existing filter UI to reuse — pass
`markets`/`availableTimeframes` + their `onChange` handlers to
`ChartToolbar` (or `ChartContainer`) to opt into that "standalone" mode.

### Connection panel

`ConnectionStatus` reports every dependency the live view has, not just the
socket: **Backend API** (status + measured latency from `/system/health`),
**WebSocket** (this browser's own connection — only the client knows it),
**Historical Sync** (age of `last_ingestion_at`, flagged past 15 minutes),
**Market State** (state-manager status + symbols tracked), **Last
Message**, **Reconnect Attempts**, and **Latency**. The system queries are
the same ones the Health page already uses, so the panel costs no new
endpoint and shares their cache.

Latency is the round-trip time of the stream's _own_ heartbeat
(`ping`→`pong`), not a REST timing — it measures the path the live data
actually travels.

### Empty states

`MarketDataNotice` replaces a bare "waiting for live data…" with the three
things a user needs to act: which precondition is missing (stored candles,
live feed, or just the first tick), whether the socket is even connected
(including "dropped, reconnecting automatically"), when the last message
arrived — and a Retry that refetches markets, metrics, stats and candles.
It renders nothing once the market is ready and a price has arrived, so a
healthy dashboard carries no notice at all.

Values that aren't known render as **"Unavailable"**, never as `—` or `0`:
a quantitative reader has to be able to tell "nothing arrived" from "the
value is zero". 24h high/low/volume carry a tooltip saying they are derived
from candles this platform has stored, not from the exchange ticker, since
they read low if candle sync has fallen behind.

### Performance considerations

- **Fetch cap**: `MAX_CHART_CANDLES` (10,000, in `hooks/use-chart-candles.ts`)
  bounds network/memory cost for a single render. Raise it there — after
  profiling shows it's actually insufficient — rather than adding a new
  endpoint; the pagination logic already scales to it.
- **No React re-renders for data pushes**: `CandlestickChart` is
  `React.memo`-wrapped and talks to lightweight-charts imperatively via
  `useEffect`s keyed on `[candlesticks, volume]`/`[theme]`/
  `[fitContentToken]` — a parent re-render that doesn't change those
  values never touches the chart. `ChartContainer` memoizes the adapter
  output (`useMemo` on `[candles, theme colors]`) so array identity is
  stable across unrelated re-renders.
- **Rendering, not fetching, is what needs to stay smooth at 10,000+
  candles** — lightweight-charts virtualizes its own canvas rendering, so
  the practical ceiling is network/JSON-parse cost for the paginated
  fetch, not chart draw performance.

### Error handling

`ChartContainer` covers: no market/timeframe selected yet (prompt), first
page loading (skeleton), an API failure at any page (`Alert` + retry,
reusing `ApiError.message` the same way the History table does), an empty
range (`Alert`, info), and unexpected data — `data-adapter.ts` drops any
candle with a non-finite OHLCV field, an unparseable timestamp, or a
timestamp duplicating one already seen, rather than feeding `NaN`/garbage
into the chart. An `invalid_timeframe` (or any other) domain error from the
backend surfaces through the same generic API-failure path — there's no
separate UI for it since the timeframe list a user can pick from already
comes from the live `/timeframes` endpoint.

### Extension points for indicators

Out of scope for this module (see `DECISIONS.md`/`PROJECT.md` for the
platform's broader AI/prediction roadmap), but the seams are:

- **`ChartContainer`** already isolates data-fetching from rendering — an
  indicator that needs its own series (e.g. a moving average) would fetch
  in a sibling hook and pass another `LineData[]`/`HistogramData[]` array
  into a new prop on `CandlestickChart`, which would call
  `chart.addSeries(LineSeries, …)` once (in the mount effect) and
  `series.setData(...)` in the existing data-push effect — no change to
  the candlestick/volume series.
- **`data-adapter.ts`** is the single place OHLCV strings become chart-ready
  numbers; a derived indicator (e.g. an SMA computed client-side) would be
  a new pure function here, tested the same way as `toChartSeries`.
- **`ChartToolbar`** has room for additional controls (e.g. an indicator
  picker) alongside the existing fit-content button.

## Live Market Dashboard

`/live-market` (`src/features/live-market/`) is a real-time monitoring page
for one symbol: current price, a live-updating candlestick chart, and a
trade tape, all sourced from the backend's own streaming gateway —
**never** a direct connection to Delta Exchange. That constraint is
architectural, not just a style preference: before this feature, the
backend had no server-to-browser push channel at all (see `docs/api/API.md`
history and the now-superseded "Known Limitations" note in `CLAUDE.md`), so
building this page required adding one —
`GET/WS /api/v1/ws/market` in `services/api/app/api/v1/endpoints/market_stream.py`,
backed by `app/marketdata/gateway.py`'s `MarketStreamGateway`. The gateway
subscribes to the same in-process event bus (`TradeEventReceived`,
`TickerUpdated`) the existing pipeline already publishes to, and fans each
event out to every browser connection subscribed to that symbol over a
per-connection bounded queue (a slow browser client drops messages and is
counted, never blocks other clients or the publisher).

### Streaming flow

```mermaid
flowchart LR
    A["Delta Exchange WebSocket\n(outbound client, app/integrations/delta)"] --> B["MarketDataPipeline\n(parse/normalize/validate)"]
    B --> C["EventBus\n(TradeEventReceived, TickerUpdated)"]
    C --> D["MarketStreamGateway\n(app/marketdata/gateway.py)"]
    D -->|"per-symbol fan-out,\nbounded per-connection queue"| E["/api/v1/ws/market\n(FastAPI WebSocket route)"]
    E --> F["useMarketStream\n(reconnect + backoff, Zod-validated)"]
    F --> G["useLiveCandle\n(client-side bar aggregation)"]
    F --> H["PriceCard / TradeTape / ConnectionStatus"]
    G --> I["ChartContainer\n(liveCandle/liveVolume props)"]
```

Protocol (JSON text frames, both directions) is documented in full at the
top of `market_stream.py`; the frontend's matching Zod schemas live in
`src/types/api/market-stream.ts`. A client must send `{"action":
"subscribe", "symbols": [...]}` to receive anything — nothing is
auto-subscribed on connect — and gets an immediate `snapshot` message (the
gateway's own read of `MarketStateManager`) so the UI isn't blank on a
quiet market while it waits for the next live event.

**Timestamp format matters here, and it broke once.** Every `event_time`
the gateway emits must end in a literal `Z`, matching the REST layer's own
`field_serializer` convention (`app/schemas/market_data.py`), because the
frontend's `z.string().datetime()` schemas accept only that literal suffix
by default — not the `+00:00` a bare Python `datetime.isoformat()`
produces. That exact mismatch once caused every trade/ticker/snapshot frame
to fail validation and be silently dropped, while heartbeat pongs (no
timestamp) kept the connection looking healthy the whole time. Fixed in
`_isoformat_utc` (`app/marketdata/gateway.py`); pinned by tests on both
sides so it can't regress silently again (`test_gateway.py`'s
`TestWireTimestampFormat`, `src/types/api/market-stream.test.ts`).

### Component hierarchy

```text
LiveMarketPage                 resolves symbol/timeframe; owns nothing else
├── ConnectionStatus           backend API, WebSocket, historical sync, market
│                              state, last message, reconnects, heartbeat latency
├── (fallback alert)           shown when resolution moved off a requested market
├── MarketDataNotice           why data is missing, and a retry — only when it is
├── PriceCard                  price/24h change (WS) + 24h high/low/volume,
│                              last trade time, last candle time (REST poll)
├── ChartContainer             reused from the chart module, in "standalone" mode
│   └── (MarketSelector / TimeframeSelector render inside its ChartToolbar)
└── TradeTape                  newest-first, capped, coloured by aggressor side
```

`PriceCard`, `TradeTape`, `ConnectionStatus` and `MarketDataNotice` are all
`React.memo`-wrapped, so a tick that only changes the trade list doesn't
re-render the connection panel.

`ChartContainer`/`CandlestickChart`/`MarketSelector`/`TimeframeSelector` are
the exact same components the History page's Chart tab uses (see "Chart
module" above) — nothing here is a copy. Live Market is precisely the
"standalone" scenario that pattern was built for: there's no pre-existing
filter form to reuse, so `ChartContainer` is given `markets`/
`availableTimeframes`/`onSymbolChange`/`onTimeframeChange` and renders its
own selectors.

### Market selection, validation and fallback

Of the ~225 markets in `/markets`, only the handful the backend actually
tracks (`DELTA_MARKET_SYMBOLS`, `BTCUSD,ETHUSD` by default) have any
candles or a live feed behind them; the rest are catalogue rows. Picking
the first market in the list therefore opened the dashboard on something
like `1000BONKUSD` with every panel empty. Selection is now _resolved_
rather than assumed, by `hooks/use-research-market.ts` over the pure rules
in `lib/market-selection.ts`:

1. **Candidate order** (`buildCandidateSymbols`): the symbol requested in
   the URL (`?symbol=`) → the symbol remembered from the last visit →
   `ETHUSD`, the primary research market → whatever the backend is
   currently streaming → any other active market. Unknown and inactive
   symbols are dropped, and the list is capped at `MAX_CANDIDATES` (6)
   because each candidate costs one timeframes probe.
2. **Validation** (`assessMarket`): a market is _ready_ when it has stored
   candles (`/markets/{symbol}/timeframes` is non-empty) **and** the
   backend is streaming it (`state_latest_prices` from `/system/metrics`
   lists it). Latest-price presence is reported separately from live
   support, because "untracked symbol" and "tracked but no tick yet" are
   different problems with different fixes.
3. **Fallback** (`selectResearchMarket`): first ready candidate → else the
   first with candles → else the first candidate. That last tier is
   deliberate: an operator running with the live feed disabled should still
   get a usable historical view instead of an empty page, so a market is
   never rejected outright — the gaps surface as `blockers` in the empty
   state instead.

Candidates are probed with `useQueries` under the same query key
`useTimeframes` uses, so a probe and the chart's own timeframe fetch share
one cache entry rather than duplicating the request.

When resolution moves away from an explicitly requested market, the page
says so ("1000BONKUSD has no research data … showing ETHUSD instead")
rather than silently substituting. The notice is captured in state at the
moment of the switch, because the URL is immediately rewritten to the
market that was actually resolved.

**Persistence**: the resolved symbol and timeframe are written to the URL
(`use-live-market-url-state.ts`, `router.replace` so market-flipping
doesn't fill the history stack) and mirrored into `localStorage`
(`lib/remembered-market.ts`, every access guarded — storage throws in
private-mode browsers). The URL is the shareable source of truth; storage
is the cross-visit fallback when the page is opened with no search params.

**Timeframe** resolution (`lib/timeframe-preference.ts`) follows the same
shape — explicit selection → URL → remembered → finest available — and
ignores any candidate the current symbol has no candles for, so a
remembered `4h` can't blank the chart on a market that only stores `1m`.

### One symbol across every widget

`ConnectionStatus`, `PriceCard`, `ChartContainer` and `TradeTape` all read
the single resolved `symbol`. Two things enforce that they can never drift
apart: `useMarketStream` clears its data synchronously when `symbol`
changes (showing the previous market's price under the new market's name
for even one frame would be a correctness bug), and it **discards any frame
whose `symbol` field doesn't match the subscription** — a message still in
flight when the user switches markets cannot be folded into the new one.

### Live candle synthesis (no backend candle-aggregation pipeline exists)

The backend has no real-time candle-close detection — `CandleClosed` bus
events are reserved for a future milestone (see
`app/events/example_events.py`); the only way historical candles reach the
database today is the periodic REST-based `CandleSyncScheduler`, not the
live tick stream. So "append new candles in real time" is implemented
entirely client-side: `use-live-candle.ts` folds each streamed trade into
the currently-forming bar (`lib/aggregate-live-candle.ts`, pure and
unit-tested), bucketing by the selected timeframe. That forming bar is
pushed into `CandlestickChart` via its `liveCandle`/`liveVolume` props,
which call lightweight-charts' `series.update()` — an O(1) append/replace
of the last bar — instead of `setData()`, satisfying "avoid full chart
re-renders" directly through the library's own incremental-update API.
The forming bar is **seeded from the last historical candle** so history
loads first and the live bar continues it rather than restarting: a trade
inside the seed's own bucket extends that bar (instead of a fresh
one-trade bar replacing it at the same timestamp), and a trade in a later
bucket opens at the seed's close rather than gapping. Once candle sync
produces a _newer_ historical bar, it supersedes the locally-synthesized
one. The seed is read through a ref, so a historical refetch — which
produces a new object every time — never re-runs the fold and
double-counts a trade.

`CandlestickChart` also refuses any `update()` whose time precedes the
newest point already in the series. That is reachable in normal operation
(a historical refetch landing while a forming bar for an earlier bucket is
still on screen) and lightweight-charts throws on it, so the update is
dropped rather than crashing the page.

### Why 24h high/low/volume are polled, not pushed

`PriceCard`'s current price and 24h change come from the live ticker
(`price_change_24h` was already on the domain `TickerEvent` model — no
backend change needed for that field). 24h high/low/volume reuse the
_existing_ `/markets/{symbol}/candles/stats` REST endpoint instead
(`use-price-stats.ts`, polled every 60s — the same polling pattern the
Health page already uses at 10s), because: (a) it needed no new backend
work at all, and (b) a rolling 24h aggregate has no reason to be
millisecond-fresh the way a live trade price does. Total volume isn't a
field the endpoint returns directly, so it's derived as `average_volume ×
total_candles` (mathematically the sum) rather than adding a field to a
response shape three other features already depend on.

### The trade tape's "Side" column

Trades carry a real aggressor side: `buy` means the taker lifted the offer,
`sell` means the taker hit the bid. `TradeTape` colors each row by that
value.

This corrects an earlier assumption. The backend normalizer used to
hard-code `side="unknown"` on the belief that Delta's public feed didn't
expose taker side, and the tape coloured rows by price direction as a
proxy. In fact the compact `trades` channel carries an `r` field the
normalizer was discarding, and it is the _buyer's role_ in the fill.
Verified against the exchange rather than assumed: 55 fills captured
simultaneously from the compact `trades` channel and the verbose
`all_trades` channel (which spells out `buyer_role`/`seller_role`) agreed
on every single one — `r="t"` ⇔ `buyer_role="taker"` (an aggressive buy),
`r="m"` ⇔ `buyer_role="maker"` (an aggressive sell), with no
counterexamples. Anything other than those two values still degrades to
`unknown` rather than being coerced into a side.

### Connection panel

`ConnectionStatus` reports every dependency the live view has, not just the
socket: **Backend API** (status + measured latency from `/system/health`),
**WebSocket** (this browser's own connection — only the client knows it),
**Historical Sync** (age of `last_ingestion_at`, flagged past 15 minutes),
**Market State** (state-manager status + symbols tracked), **Last
Message**, **Reconnect Attempts**, and **Latency**. The system queries are
the same ones the Health page already uses, so the panel costs no new
endpoint and shares their cache.

Latency is the round-trip time of the stream's _own_ heartbeat
(`ping`→`pong`), not a REST timing — it measures the path the live data
actually travels.

### Empty states

`MarketDataNotice` replaces a bare "waiting for live data…" with the three
things a user needs to act: which precondition is missing (stored candles,
live feed, or just the first tick), whether the socket is even connected
(including "dropped, reconnecting automatically"), when the last message
arrived — and a Retry that refetches markets, metrics, stats and candles.
It renders nothing once the market is ready and a price has arrived, so a
healthy dashboard carries no notice at all.

Values that aren't known render as **"Unavailable"**, never as `—` or `0`:
a quantitative reader has to be able to tell "nothing arrived" from "the
value is zero". 24h high/low/volume carry a tooltip saying they are derived
from candles this platform has stored, not from the exchange ticker, since
they read low if candle sync has fallen behind.

### Performance considerations

- **Batched stream commits**: incoming frames are buffered and committed to
  React state at most once per animation frame (`requestAnimationFrame`)
  rather than one `setState` per message. A busy market prints many trades
  per second, and a commit per print would re-render the price card, chart
  and tape on every one; batching to the paint cycle keeps a whole burst
  within one frame down to a single commit, self-limits to the display's
  own refresh rate, and pauses entirely while the tab is backgrounded (rAF
  callbacks don't run for hidden tabs). A burst of 20 prints landing as one
  commit is asserted in `use-market-stream.test.ts`, which also confirms
  the scheduling call is `requestAnimationFrame` itself (not a fixed
  timer) and that a pending frame is cancelled on unmount. This was
  originally a fixed 100ms `setTimeout`; switched to rAF during the Order
  Book viewer's performance pass — see FRONTEND.md § "Live Order Book
  Viewer → Performance considerations" for the full reasoning, which
  applies to this page too since they share the hook.
- **Per-consumer channel tracking**: `useMarketStream`'s `channels` option
  (`{ trades, ticker, orderBook }`, all on by default here) lets a caller
  that doesn't need every message type opt out — a message on a disabled
  channel is dropped before it touches the pending buffer or schedules a
  commit. The Live Market Dashboard tracks everything (it uses all three),
  but the Order Book viewer disables trades/ticker entirely; see that
  page's docs for why this mattered in practice.
- **No new WebSocket per re-render**: `useMarketStream`'s connection
  lifecycle lives in a single `useEffect` keyed on `[symbol, streamUrl]`.
  A symbol change tears down and reopens the connection deliberately;
  nothing else re-rendering the page does. `maxTrades` and `channels` are
  both read through refs precisely so changing either can't force a
  reconnect.
- **Memoized widgets**: the four panels are `React.memo`-wrapped and the
  page passes memoized `liveCandle`/`liveVolume` objects, so an update that
  changes only one of them doesn't re-render the rest.
- **Reconnect backoff**: exponential, `1s × 2^attempt` capped at 30s, mirroring
  the backend's own `DeltaWebSocketClient` reconnect strategy conceptually
  (see `services/api/app/ws/connection.py`) without sharing code — one is a
  Python outbound client, the other a browser `WebSocket`.
- **Bounded trade tape**: `useMarketStream`'s `maxTrades` option caps both
  the buffer and the rendered list (default 100) — high-frequency streams
  can't grow either unbounded. The cap is shown in the tape's header so it
  isn't a mystery why the list stops.
- **Chart updates stay O(1) per tick**: see "Live candle synthesis" above —
  this is what actually keeps a fast-ticking market smooth, not React-level
  memoization alone.
- **Backend fan-out never blocks on a slow client**: each browser
  connection's outbound queue is bounded (`MarketStreamGateway`); a full
  queue drops the message and increments a metric instead of backing up
  the event bus's publish path for every other connection.

## Live Order Book Viewer

`/orderbook` (`src/features/order-book/`) is a live depth-table view for
one symbol — synchronized bid/ask tables with cumulative-depth bars, a
spread summary, and a depth selector (10/25/50/100 levels) — sourced from
the same backend gateway the Live Market Dashboard uses.

### Why this needed a new backend component, not just a new endpoint

The event bus already carried order-book data (`OrderBookUpdated` /
`OrderBookEvent`) before this feature — the Delta pipeline normalizes
`ob_l1`/`ob_l2`/`ob_updates` channel messages into it, and
`MarketStateManager` already stored the latest one per symbol. But
`MarketStateManager`'s own docstring is explicit that it does _not_
reconstruct a coherent order book — "order book reconstruction from
seq/checksum is a consumer concern" — and Delta's live `ob_updates`
channel is a snapshot **followed by incremental diffs of only the changed
price levels** (`action: "update"`, where a `size: 0` level means "remove
it," not "size is now zero"). Storing the latest message verbatim, as the
state manager does, would replace the whole reconstructed book with just
the handful of levels in the most recent diff on every tick — a real,
verified defect: `ob_l1` alone was observed firing ~10 times/second with
only the top bid/ask level, which would have wiped a multi-thousand-level
book down to one level ten times a second had it been relayed naively.

The fix was a new backend component,
`services/api/app/marketdata/orderbook.py`'s `OrderBookAggregator` — the
missing "consumer" the state manager's docstring pointed at. It subscribes
to the same `OrderBookUpdated` bus event, replaces the book on a snapshot,
and merges diffs (upsert non-zero sizes, drop zero-size levels) on an
update, deliberately ignoring `kind == "l1"` events since they'd corrupt
the reconstructed depth the same way. `MarketStreamGateway` was extended
to read the aggregator's current top-100-per-side view (not the raw bus
event) on every update and relay it as a new `orderbook` message type —
`services/api/app/api/v1/endpoints/market_stream.py`'s protocol docstring
has the exact wire shape. No new WebSocket endpoint was added; this is the
same `/api/v1/ws/market` gateway, extended.

### Streaming flow

```mermaid
flowchart LR
    A["Delta ob_updates channel
(snapshot + incremental diffs)"] --> B["MarketDataPipeline
(normalizes to OrderBookEvent)"]
    B --> C["EventBus
(OrderBookUpdated)"]
    C --> D["OrderBookAggregator
(app/marketdata/orderbook.py)
replaces on snapshot, merges on diff"]
    D --> E["MarketStreamGateway
(reads the aggregator's current book)"]
    E -->|"sorted, top-100/side,
per-symbol fan-out"| F["/api/v1/ws/market"]
    F --> G["useMarketStream
(latestOrderBook — reused from Live Market)"]
    G --> H["computeDepthRows / computeSpread
(order-book-depth.ts, pure)"]
    H --> I["OrderBookTable × 2 / SpreadPanel"]
```

### Reuse over duplication

This feature deliberately shares infrastructure with the Live Market
Dashboard rather than standing up parallel plumbing:

- **`useMarketStream`** (`src/features/live-market/hooks/`) is the exact
  same hook, extended with a `latestOrderBook` field rather than forked —
  it already owns the one WebSocket connection/reconnect/batching
  lifecycle this page needs, for the same gateway and the same per-symbol
  subscription model. This page passes `maxTrades: 0` since it has no
  trade tape.
- **`MarketSelector`** (`src/components/chart/market-selector.tsx`) is
  reused as-is, the same "standalone" component the chart module exports.
- **`ConnectionStatus`** (`src/features/live-market/components/`) is
  imported directly rather than copied — it already reports every
  dependency this page has too (backend API, WebSocket, historical sync,
  market state, last message, reconnects, heartbeat latency).
- **`buildCandidateSymbols`** (`src/features/live-market/lib/market-selection.ts`)
  is reused for candidate _ordering_ (URL → remembered → `ETHUSD` →
  live-tracked → any active), but **not** the Live Market Dashboard's
  candle-aware readiness/fallback machinery (`assessMarket`/
  `selectResearchMarket`) — an order book has no notion of stored candles,
  so `hooks/use-order-book-market.ts` implements its own, simpler
  readiness rule (is the symbol in `/system/metrics`'s
  `state_latest_prices`?) on top of the shared ordering policy. Forcing
  the candle-aware version would have gated an order-book-ready market on
  an irrelevant check.
- **`remembered-market.ts`** (`src/features/live-market/lib/`) is reused
  as-is — the "last market I was looking at" preference is shared across
  Live Market and Order Book by design, not a coupling accident.

One deliberate behavioral difference from Live Market: an **explicitly
requested** symbol (`?symbol=` present right now) is always honoured
verbatim here, even if it turns out to be untracked — `OrderBookEmptyState`
explains why rather than the page silently substituting a different
market. A merely _remembered_ symbol from a previous visit gets no such
guarantee and falls back to a live-tracked candidate if it's stale.

### Component hierarchy

```text
OrderBookPage                  resolves symbol; owns the depth selection
├── ConnectionStatus           reused from Live Market, unmodified
├── MarketSelector             reused from the chart module
├── DepthSelector               10/25/50/100, same ToggleButtonGroup pattern
│                              as the chart module's TimeframeSelector
├── OrderBookEmptyState        untracked / no snapshot yet / empty book
├── SpreadPanel                 best bid/ask, spread, spread %, mid price
└── OrderBookTable × 2           "bids" and "asks" — one component, mirrored
```

`OrderBookTable` is one `React.memo`-wrapped component parameterized by
`side`, not two near-duplicate components — sort order, bar-growth edge,
and color are the only differences and all three already follow from
`side`.

### Depth visualization

Each row's cumulative `total` (running sum of size from the best price
outward) and a `depthRatio` (that row's total as a fraction of the
deepest visible row) are computed once per update in
`lib/order-book-depth.ts`'s `computeDepthRows` — pure, unit-tested, and
re-sliced (not re-sorted: the gateway already sorts) whenever the depth
selector changes. The bar itself is a CSS `linear-gradient` background on
the table row, not an extra absolutely-positioned element — bids grow
from the right edge, asks from the left, so the two tables read as a
mirrored pair when placed side by side.

### Why spread/mid-price can go entirely `Unavailable`

`computeSpread` requires _both_ sides to have at least one level; a
one-sided book (e.g. momentarily during a resync) reports every field —
best bid, best ask, spread, spread %, mid price — that depends on the
missing side as `Unavailable`, never a misleading zero spread synthesized
from a partial book.

### Performance considerations

This page went through a dedicated optimization pass after the initial
implementation, once it was flagged as functionally complete but not yet
production-ready for high-frequency streaming. The concrete findings and
fixes:

**Finding: the page re-rendered on every trade and ticker tick, not just
order-book ticks.** `useMarketStream` is one hook shared with the Live
Market Dashboard, and subscribing to a symbol means the gateway sends
trade, ticker, _and_ order-book messages together — there's no
server-side channel filter. Before this pass, every trade print (the
highest-frequency message type observed against the real feed) still
pushed into an internal buffer and triggered a commit, even though this
page never reads `latestTrade`/`latestTicker`/`trades` at all. Fixed with
a new `channels` option on `useMarketStream` (`{ trades, ticker,
orderBook }`, all on by default for the Live Market Dashboard): a message
on a disabled channel is dropped before it touches the pending buffer _or_
schedules a commit — no array push, no new object reference, no
`setState`. This page passes `channels: { trades: false, ticker: false,
orderBook: true }`. `lastMessageAt` is scoped to the channels an instance
actually tracks as a direct consequence (documented on the option itself)
— flushing purely to bump a timestamp nobody reads would be the very
re-render this option exists to prevent; a heartbeat pong (every 15s)
still bounds how stale it can get.

**Finding: batching was on a fixed 100ms timer, not tied to the browser's
own paint cycle.** `useMarketStream` used to coalesce updates via
`setTimeout(flush, 100)`. Switched to `requestAnimationFrame`: a burst of
messages within one frame still coalesces into a single commit exactly as
before, but the commit now lands right before the browser's next paint
(never wasted between frames), the effective rate self-limits to the
display's own refresh rate rather than an arbitrary interval, and —
without any extra code — the entire pipeline pauses itself whenever the
tab is backgrounded, since browsers don't run rAF callbacks for hidden
tabs. This is a real, verified CPU saving for a tab left open in the
background, not just a smoothness tweak.

**Finding: no row-level memoization — every row re-rendered on every
update, even unaffected ones.** `computeDepthRows` legitimately returns a
brand-new array of brand-new row objects on every call (the book really
did change), so a plain `OrderBookTable` mapping `rows` inline gave React
no way to skip re-rendering (and re-diffing three `<TableCell>`s' worth of
formatting calls) for a row whose values hadn't actually moved. Fixed by
extracting `OrderBookRow` as its own component wrapped in
`React.memo(OrderBookRowInner, orderBookRowPropsAreEqual)`, where the
comparator (exported, unit-tested directly in
`order-book-table.test.tsx`) compares the four values that reach the DOM
— `price`, `size`, `total`, `depthRatio` — **by value**, not by object
reference. This is the mechanism behind "only changed price levels
update": a row above the point of change in the book, or every row on the
side of the book the update didn't touch (the gateway always resends both
sides together — see below), now genuinely skips re-rendering, keyed
stably by `row.price` (a level's natural, unique identity) so React
matches the right row across updates regardless of it being a new object.
One caveat inherent to the feature, not fixable by memoization: cumulative
`total` is a running sum from the best price outward, so a change at
price level _N_ still invalidates every row below it — no memoization
scheme can avoid that without changing what "cumulative depth" means.

- **No second WebSocket connection**: reusing `useMarketStream` means this
  page still gets the Live Market Dashboard's reconnect backoff and
  symbol-filtering for free — see FRONTEND.md § "Live Market Dashboard →
  Performance considerations" for those details, unchanged by this pass.
- **Backend does the sort and the depth cap**: `OrderBookAggregator`
  maintains the full book internally (bounded by the market's own price
  granularity — a few thousand levels, trivial memory) but the gateway
  only ever relays the top 100 per side
  (`app/marketdata/gateway.py`'s `_ORDERBOOK_DEPTH`), and always resends
  **both** sides on any update (it doesn't track which side changed) —
  the frontend never re-sorts (the backend's order is trusted verbatim;
  `lib/order-book-depth.test.ts` pins this by asserting on unsorted mock
  input) and never receives more than a client could ever choose to
  display.
- **Depth-selector changes never refetch**: switching 10/25/50/100 just
  re-slices the already-received `latestOrderBook` array
  (`computeDepthRows`), a synchronous, memoized (`useMemo`) operation with
  no network round-trip. Note that a depth change _does_ legitimately
  re-render every row — `depthRatio` is normalized against the deepest row
  in the new slice, so the denominator itself changes for every row; this
  is real, necessary work, not something left unoptimized.
- **Memoized panels and callbacks**: `SpreadPanel`, `OrderBookTable`, and
  `OrderBookEmptyState` are all `React.memo`-wrapped, the page passes
  memoized `bidRows`/`askRows`/`spread` (`useMemo` keyed on the raw levels
  and selected depth) and memoized `handleSymbolChange`/`handleRetry`
  (`useCallback`), and `EMPTY_LEVELS`/`ORDER_BOOK_CHANNELS` are stable
  module-level constants rather than fresh literals on every render — so
  an unrelated re-render (e.g. the connection panel's clock tick) never
  cascades into recomputing or re-rendering the tables.
- **No unbounded growth**: nothing in this page's state accumulates over
  time. `latestOrderBook` is _replaced_, never appended to; the disabled
  `trades` channel means the trade buffer stays permanently empty rather
  than growing and being trimmed; the backend's `OrderBookAggregator`
  is bounded by the market's own distinct price count, not by how long the
  connection has been open. A multi-hour session should show flat memory,
  though verifying that empirically requires a real browser session this
  environment has no way to drive (see "Known scalability limits" below).

### Error handling

`OrderBookEmptyState` covers: an untracked market (explicitly requested or
not), no snapshot received yet (split into "connected, just quiet" vs.
"reconnecting" vs. "not connected") with a retry, and a genuinely empty
reconstructed book (both sides empty — a valid, if unusual, state,
distinct from "no book yet"). An invalid payload (fails
`LiveOrderBookDataSchema`) is dropped by `useMarketStream`'s existing
Zod-validation gate — the same silent-drop-and-keep-the-old-value
behavior as every other message type on this gateway, verified with a
malformed `orderbook` frame in `order-book-page.test.tsx`.

### Extension points

- **Depth beyond 100**: raise `_ORDERBOOK_DEPTH` in
  `app/marketdata/gateway.py` and `DEPTH_OPTIONS` in
  `lib/order-book-depth.ts` together — both already scale to it, this is a
  constant change, not a redesign.
- **Sequence/checksum validation**: `OrderBookAggregator` trusts stream
  order and does not validate Delta's per-message sequence number or
  checksum (`cs`) — documented, not fixed, in its module docstring. A
  dropped connection self-heals (resubscribe always re-triggers a fresh
  snapshot); a gap _within_ a connected session would not be caught today.
- **A combined center-book view**: the two-table layout was chosen to
  match the task's explicit "two synchronized tables" requirement; nothing
  about `computeDepthRows`/`computeSpread` assumes two separate tables — a
  future single merged-ladder view could reuse both unchanged.

### Known scalability limits

- **No per-connection channel filtering on the wire.** The `channels`
  option (above) is a frontend-only filter — the backend still sends
  trade and ticker frames to every subscriber of a symbol regardless of
  what any given browser tab actually tracks, so the _network_ cost of an
  unused channel isn't eliminated, only the client-side processing/render
  cost of it. Fixing the wire cost too would need a gateway protocol
  change (e.g. a `channels` field on the `subscribe` action) — a
  reasonable next step if profiling ever shows inbound bandwidth, not
  render cost, as the bottleneck.
- **Row memoization's benefit shrinks for changes near the best price.**
  Because `total` is a cumulative running sum, a change to the
  best-priced level invalidates every row below it in the same slice — on
  a very actively-traded book where changes cluster at the top, most rows
  in a 100-level view may still re-render on a given tick. The two
  documented full wins are: a row above wherever the change occurred, and
  the entire opposite side of the book when only one side actually moved.
- **No empirical, multi-hour browser verification.** This optimization
  pass was verified by (a) unit-testing the actual mechanisms directly —
  the `React.memo` comparator, the `requestAnimationFrame` scheduling, and
  the channel-gating behavior — and (b) code-level inspection confirming
  no state accumulates over time (see "Performance considerations"
  above), rather than by driving a real browser for 15+ minutes and
  watching DevTools' Performance/Memory panels, since no browser
  automation tool is available in this environment. The reasoning is
  sound and the mechanisms are directly tested, but a real long-running
  session (React DevTools Profiler flame graphs, an actual heap snapshot
  diff) has not been captured and would be the natural next validation
  step before a production rollout at real trading-desk scale.

## State management

- Server state: TanStack Query (`src/lib/query/queryClient.ts`).
- Local UI state: Zustand (`src/store/ui-store.ts` — sidebar state only
  today).
- The chart module keeps its own crosshair-hover state
  (`useState` in `ChartContainer`) — it is presentation-only and does not
  belong in Zustand.
- The Live Market Dashboard's connection/trade/ticker state
  (`useMarketStream`) and forming-candle state (`useLiveCandle`) are also
  plain React state, not Zustand: this state is owned by exactly one page
  instance at a time and nothing else in the app needs to read it, so a
  global store would add indirection without solving a real cross-component
  sharing problem. Zustand remains the right tool for state genuinely
  shared across the component tree (like the sidebar).

## Testing

See [`TESTING.md`](TESTING.md) for the frontend testing strategy in full;
in short, Vitest + Testing Library, with `lightweight-charts`'s `createChart`
mocked wherever `CandlestickChart` is rendered (jsdom has no real canvas 2D
context).

## Conventions

- Server components by default; `'use client'` only where interactivity is
  needed.
- All API payloads validated with Zod schemas in `src/types/api/`.
- Feature logic in `src/features/<feature>/`; cross-feature/reusable code
  in `src/components/` and `src/lib/` (the chart module lives in
  `src/components/chart/` precisely because it isn't specific to History).
