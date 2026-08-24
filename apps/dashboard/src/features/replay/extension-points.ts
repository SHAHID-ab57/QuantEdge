import type { ReplayClock } from './engine/replay-clock';
import type { Candle } from '@/types/api/market';

/**
 * Documents where future replay capabilities plug into the engine built
 * here, without speculatively implementing any of them now (see
 * `FRONTEND.md` § "Historical Market Replay Engine → Extension points" for
 * the full rationale). Nothing in this file is wired into the page today —
 * it exists so a future implementer has a concrete seam to extend rather
 * than needing to re-architect `useReplayEngine`/`useReplayChartSync`.
 *
 * Why trades and order books aren't replayed today: `services/api/app/models/`
 * defines exactly three persisted tables — `Exchange`, `Market`, and
 * `Candle` (verified by reading the backend's model directory during this
 * feature's design, not assumed). There is no historical tick-level trade
 * log and no historical order-book snapshot store, so there is nothing to
 * paginate and replay beyond OHLCV candles. Rather than synthesizing fake
 * trade prints from candle closes — which would look real on screen while
 * being fabricated, the opposite of what a quantitative research tool
 * should show — this feature replays exactly what the backend actually
 * persisted, and leaves the seams below for whenever a historical trade/
 * order-book log becomes a real backend feature.
 *
 * ## How every module below actually synchronizes: subscribe to `ReplayClock`
 *
 * `useReplayEngine` exposes one `ReplayClock` instance (`engine/replay-clock.ts`)
 * that is the single source of "what candle/timestamp/phase/speed replay is
 * at right now." `ReplayChart` already reads it, via
 * `useReplayClockTick(engine.clock)` in `replay-page.tsx` — a
 * `useSyncExternalStore`-backed hook (`hooks/use-replay-clock.ts`). Every
 * interface below is what a *second* subscriber would additionally need
 * beyond that same tick: none of them re-derive "where is replay right
 * now" on their own, which is what would let a future module drift out of
 * sync with the chart (e.g. an indicator computed one candle ahead of what
 * the chart is showing). A new module's shape is therefore always
 * `{ ...moduleSpecificData, tick: ReplayClockTick }` in spirit, even though
 * the interfaces below spell out only the additional fields for clarity.
 *
 * What a future historical trade source would need to supply: one page of
 * trades within a time range, shaped so `useReplayEngine`'s index-driven
 * stepping model extends to it directly — a trade source would be loaded
 * and stepped through exactly like `Candle[]` is today, keyed by its own
 * timestamp field. The Live Trade Analytics dashboard's `TradeTape`
 * (`src/features/live-market/components/trade-tape.tsx`) already accepts
 * a plain `LiveTradeData[]` and would need no changes to render a replayed
 * slice of this shape — only a new backend endpoint and a sibling to
 * `useReplayCandles` would be new work.
 */
export interface HistoricalTradeSource {
  fetchTrades(params: {
    symbol: string;
    start: string;
    end: string;
  }): Promise<{ trades: Array<{ price: string; size: string; side: string; event_time: string }> }>;
}

/**
 * What a future Trade Tape replay sync would actually consume once loaded:
 * every trade up to the clock's current timestamp, plus the clock itself —
 * not a separately-tracked index. Subscribing to `engine.clock` (the exact
 * instance `ReplayChart` already reads) is what guarantees the tape can
 * never show a trade from a moment the chart hasn't reached yet.
 */
export interface ReplayTradeSyncInput {
  clock: ReplayClock;
  loadedTrades: ReadonlyArray<{ price: string; size: string; side: string; event_time: string }>;
}

/**
 * What a future historical order-book source would need to supply: one
 * snapshot per requested timestamp (not a continuous stream — a
 * reconstructed L2 book, the same shape `OrderBookAggregator`
 * (`services/api/app/marketdata/orderbook.py`) already produces for the
 * *live* Order Book viewer). The existing viewer's table/spread components
 * (`src/features/order-book/`) already accept that reconstructed shape and
 * would not need to change; only a historical snapshot store and this
 * fetch function would be new.
 */
export interface HistoricalOrderBookSource {
  fetchSnapshotAt(params: { symbol: string; timestampMs: number }): Promise<{
    bids: Array<{ price: string; size: string }>;
    asks: Array<{ price: string; size: string }>;
  }>;
}

/**
 * What a future Order Book replay sync would consume: the clock (to know
 * which snapshot timestamp to request/display) plus whatever local cache
 * of already-fetched snapshots the sync layer maintains — the existing
 * viewer's table/spread components render from that cache unmodified.
 */
export interface ReplayOrderBookSyncInput {
  clock: ReplayClock;
  snapshotAt: (timestampMs: number) => {
    bids: Array<{ price: string; size: string }>;
    asks: Array<{ price: string; size: string }>;
  } | null;
}

/**
 * The shape a future indicator layer would consume: the clock (for the
 * current timestamp/index) plus the exact candles currently revealed
 * (`useReplayEngine`'s `candles.slice(0, currentIndex + 1)`), so an
 * indicator recomputes only over data the replay has actually shown so
 * far — never peeking ahead at future candles, which is the one
 * correctness property a backtesting-oriented indicator absolutely cannot
 * violate.
 */
export interface ReplayIndicatorInput {
  clock: ReplayClock;
  revealedCandles: readonly Candle[];
}

/**
 * The shape a future AI-prediction-playback layer would consume: the same
 * clock and revealed-candles view as `ReplayIndicatorInput`, plus the
 * actual next candle (only once replay has advanced past it) so a
 * prediction made at the clock's current index can be graded against what
 * actually happened — the playback mechanism this whole engine exists to
 * support, per the project's stated roadmap. Not implemented here; this
 * platform has no prediction model or AI feature to plug in yet (see
 * `PROJECT.md`).
 */
export interface ReplayPredictionInput {
  clock: ReplayClock;
  revealedCandles: readonly Candle[];
  /** Only populated once replay has advanced past this point — never available for peeking ahead. */
  actualNextCandle: Candle | null;
}

/**
 * The shape a future paper-trading layer would consume to simulate a fill:
 * the clock (for the current candle, the "market price" a simulated order
 * would execute against) plus the engine's own playback controls, so a
 * paper-trading UI could pause replay while a simulated order is open and
 * resume it once the user acts — reusing `useReplayEngine`'s existing
 * `pause`/`resume` rather than a second, competing playback mechanism.
 */
export interface ReplayPaperTradingInput {
  clock: ReplayClock;
  pauseReplay: () => void;
  resumeReplay: () => void;
}

/**
 * The shape a future backtesting harness would consume: the clock (so a
 * backtest run's own "current bar" is always defined the same way replay's
 * chart defines it) plus every candle revealed so far — a backtest that
 * subscribes here gets, for free, the same "never see the future" guarantee
 * `ReplayIndicatorInput`/`ReplayPredictionInput` document above, since it
 * is reading from the identical source.
 */
export interface ReplayBacktestInput {
  clock: ReplayClock;
  revealedCandles: readonly Candle[];
}
