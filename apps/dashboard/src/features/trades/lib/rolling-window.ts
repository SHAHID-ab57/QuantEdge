import type { TradeRecord } from './trade-record';

/**
 * The live-activity indicator's window. Deliberately much shorter than the
 * one-minute figures: a "trades per second" readout is meant to feel
 * immediate, and dividing a one-minute count by 60 would lag a burst or a
 * sudden lull by up to a minute.
 */
export const TEN_SECONDS_MS = 10_000;
export const ONE_MINUTE_MS = 60_000;
export const FIVE_MINUTES_MS = 5 * ONE_MINUTE_MS;
export const FIFTEEN_MINUTES_MS = 15 * ONE_MINUTE_MS;

/** The longest window any calculation here needs. */
export const MASTER_WINDOW_MS = FIFTEEN_MINUTES_MS;

/**
 * Drops every record older than `windowMs` relative to `nowMs`. Trades
 * arrive in increasing timestamp order, so expired entries are always a
 * prefix of the array — this is an O(k) trim (k = however many just
 * expired), never an O(n) full-array re-scan. Kept for callers that already
 * have an array they want trimmed in place conceptually (returns a new
 * array, never mutates); `withinWindow` below is the read-time equivalent
 * used by the VWAP/rolling-analytics calculations.
 */
export function pruneExpired(
  records: TradeRecord[],
  nowMs: number,
  windowMs: number,
): TradeRecord[] {
  const cutoff = nowMs - windowMs;
  let start = 0;
  while (start < records.length && records[start]!.timestampMs < cutoff) {
    start += 1;
  }
  return start === 0 ? records : records.slice(start);
}

/** Volume-weighted average price over `records`, or `null` if empty. */
export function computeRollingVwap(records: readonly TradeRecord[]): number | null {
  if (records.length === 0) {
    return null;
  }
  let notional = 0;
  let volume = 0;
  for (const record of records) {
    notional += record.value;
    volume += record.size;
  }
  return volume > 0 ? notional / volume : null;
}

export interface VwapSet {
  /** Since this page connected to the symbol — see `session-stats.ts`. */
  session: number | null;
  oneMinute: number | null;
  fiveMinute: number | null;
  fifteenMinute: number | null;
}

/**
 * `records` is the engine's rolling buffer, which is only capacity-bounded
 * (see `RingBuffer`/`TradeAnalyticsEngine`) — every window here, including
 * the 15-minute one, is filtered by timestamp at read time rather than
 * assuming the caller already trimmed it, so a trade that is merely
 * *retained* (within capacity) but past its time window can never leak into
 * a figure it doesn't belong in.
 */
export function computeVwapSet(
  records: readonly TradeRecord[],
  nowMs: number,
  sessionVwap: number | null,
): VwapSet {
  return {
    session: sessionVwap,
    oneMinute: computeRollingVwap(withinWindow(records, nowMs, ONE_MINUTE_MS)),
    fiveMinute: computeRollingVwap(withinWindow(records, nowMs, FIVE_MINUTES_MS)),
    fifteenMinute: computeRollingVwap(withinWindow(records, nowMs, FIFTEEN_MINUTES_MS)),
  };
}

export interface RollingAnalytics {
  tradesPerMinute: number;
  volumePerMinute: number;
  /** Trades per second over the trailing ten seconds — the live-activity indicator. */
  tradesPerSecond: number;
  /** Buy/sell volume within the trailing one-minute window — the components of `buySellImbalance`, exposed for gauges/sparklines. */
  buyVolume: number;
  sellVolume: number;
  avgTradeSize: number | null;
  largestTrade: TradeRecord | null;
  /** `(buyVolume - sellVolume) / (buyVolume + sellVolume)`, in [-1, 1]; `null` if both are zero. */
  buySellImbalance: number | null;
}

/**
 * "Per minute" here is literal — these are the raw counts/sums observed in
 * the trailing one-minute window, not a longer window's total divided down
 * to a rate. `records` need not be pre-pruned; this filters to the last
 * minute itself.
 */
export function computeRollingAnalytics(
  records: readonly TradeRecord[],
  nowMs: number,
): RollingAnalytics {
  const window = withinWindow(records, nowMs, ONE_MINUTE_MS);
  let volume = 0;
  let buyVolume = 0;
  let sellVolume = 0;
  let largestTrade: TradeRecord | null = null;
  for (const record of window) {
    volume += record.size;
    if (record.side === 'buy') {
      buyVolume += record.size;
    } else if (record.side === 'sell') {
      sellVolume += record.size;
    }
    if (largestTrade === null || record.value > largestTrade.value) {
      largestTrade = record;
    }
  }
  const sideVolume = buyVolume + sellVolume;
  return {
    tradesPerMinute: window.length,
    volumePerMinute: volume,
    tradesPerSecond: withinWindow(records, nowMs, TEN_SECONDS_MS).length / (TEN_SECONDS_MS / 1_000),
    buyVolume,
    sellVolume,
    avgTradeSize: window.length > 0 ? volume / window.length : null,
    largestTrade,
    buySellImbalance: sideVolume > 0 ? (buyVolume - sellVolume) / sideVolume : null,
  };
}

/**
 * Records are time-sorted ascending (arrival order), so the first index
 * whose timestamp falls inside the window is found by binary search —
 * O(log n) rather than a full O(n) scan/filter over the whole (capacity-
 * bounded, potentially several-thousand-entry) buffer for every recompute.
 */
function withinWindow(
  records: readonly TradeRecord[],
  nowMs: number,
  windowMs: number,
): TradeRecord[] {
  const cutoff = nowMs - windowMs;
  let lo = 0;
  let hi = records.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (records[mid]!.timestampMs < cutoff) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return records.slice(lo);
}
