import type { TradeRecord } from './trade-record';

/**
 * Running totals for every trade seen since the page connected to this
 * symbol — "session" meaning since this browser tab subscribed, not the
 * exchange's own trading-session boundary (the platform has no historical
 * trade log to reconstruct that from; only OHLCV candles are stored — see
 * `docs/domain/MarketDataDomain.md`). Deliberately O(1) per trade and O(1)
 * in memory regardless of how long the session runs: folding a trade in
 * only updates a handful of running sums, never appends to an
 * ever-growing array that would have to be re-summed (and would grow
 * without bound) on every tick.
 */
export interface SessionAccumulator {
  count: number;
  buyVolume: number;
  sellVolume: number;
  totalVolume: number;
  buyNotional: number;
  sellNotional: number;
  totalNotional: number;
  largestTrade: TradeRecord | null;
  /** The most recent trade seen — the source of "Current Price" and its side colouring. */
  lastTrade: TradeRecord | null;
  /** Highest/lowest traded price this session. Tracked here rather than derived from the
   *  rolling window, which only retains 15 minutes and would silently "forget" a session high. */
  high: number | null;
  low: number | null;
}

export function createSessionAccumulator(): SessionAccumulator {
  return {
    count: 0,
    buyVolume: 0,
    sellVolume: 0,
    totalVolume: 0,
    buyNotional: 0,
    sellNotional: 0,
    totalNotional: 0,
    largestTrade: null,
    lastTrade: null,
    high: null,
    low: null,
  };
}

/**
 * Folds one trade into the accumulator. Pure — returns a new object rather
 * than mutating `previous` — but still O(1): every field is a running sum
 * or a single comparison, never a re-derivation from stored history.
 * "Unknown"-side trades (see `app/marketdata/normalizer.py` for when that
 * can happen) count toward the total but not toward either side's volume,
 * since attributing them to a side would be a guess this platform doesn't
 * make elsewhere either.
 */
export function foldTradeIntoSession(
  previous: SessionAccumulator,
  trade: TradeRecord,
): SessionAccumulator {
  return {
    count: previous.count + 1,
    buyVolume: previous.buyVolume + (trade.side === 'buy' ? trade.size : 0),
    sellVolume: previous.sellVolume + (trade.side === 'sell' ? trade.size : 0),
    totalVolume: previous.totalVolume + trade.size,
    buyNotional: previous.buyNotional + (trade.side === 'buy' ? trade.value : 0),
    sellNotional: previous.sellNotional + (trade.side === 'sell' ? trade.value : 0),
    totalNotional: previous.totalNotional + trade.value,
    largestTrade:
      previous.largestTrade === null || trade.value > previous.largestTrade.value
        ? trade
        : previous.largestTrade,
    lastTrade: trade,
    high: previous.high === null || trade.price > previous.high ? trade.price : previous.high,
    low: previous.low === null || trade.price < previous.low ? trade.price : previous.low,
  };
}

export interface SessionStats {
  buyVolume: number;
  sellVolume: number;
  totalVolume: number;
  /** `buyVolume / sellVolume`, or `null` when there's no sell volume to divide by. */
  buySellRatio: number | null;
  /** `totalVolume / count`, or `null` before the first trade. */
  avgTradeSize: number | null;
  largestTrade: TradeRecord | null;
  tradeCount: number;
  /** Volume-weighted average price over every trade this session, or `null` before the first one. */
  sessionVwap: number | null;
  /** `totalNotional / count` — the baseline the trade tape's "unusually large" highlight compares against. */
  avgTradeValue: number | null;
  /** Most recent traded price, or `null` before the first trade. */
  lastPrice: number | null;
  /** Aggressor side of the most recent trade — colours the Current Price readout. */
  lastSide: TradeRecord['side'] | null;
  sessionHigh: number | null;
  sessionLow: number | null;
}

export function deriveSessionStats(acc: SessionAccumulator): SessionStats {
  return {
    buyVolume: acc.buyVolume,
    sellVolume: acc.sellVolume,
    totalVolume: acc.totalVolume,
    buySellRatio: acc.sellVolume > 0 ? acc.buyVolume / acc.sellVolume : null,
    avgTradeSize: acc.count > 0 ? acc.totalVolume / acc.count : null,
    largestTrade: acc.largestTrade,
    tradeCount: acc.count,
    sessionVwap: acc.totalVolume > 0 ? acc.totalNotional / acc.totalVolume : null,
    avgTradeValue: acc.count > 0 ? acc.totalNotional / acc.count : null,
    lastPrice: acc.lastTrade?.price ?? null,
    lastSide: acc.lastTrade?.side ?? null,
    sessionHigh: acc.high,
    sessionLow: acc.low,
  };
}
