import { describe, expect, it } from 'vitest';
import type { TradeRecord } from './trade-record';
import {
  computeRollingAnalytics,
  computeRollingVwap,
  computeVwapSet,
  FIFTEEN_MINUTES_MS,
  FIVE_MINUTES_MS,
  ONE_MINUTE_MS,
  pruneExpired,
} from './rolling-window';

function record(timestampMs: number, overrides: Partial<TradeRecord> = {}): TradeRecord {
  return { price: 100, size: 1, value: 100, side: 'buy', timestampMs, ...overrides };
}

describe('pruneExpired', () => {
  it('drops records older than the window relative to now', () => {
    const records = [record(0), record(1_000), record(2_000)];
    expect(pruneExpired(records, 2_500, 1_000).map((r) => r.timestampMs)).toEqual([2_000]);
  });

  it('keeps everything when nothing has expired', () => {
    const records = [record(1_000), record(2_000)];
    expect(pruneExpired(records, 2_000, 5_000)).toEqual(records);
  });

  it('drops everything when the whole buffer has expired', () => {
    const records = [record(0), record(100)];
    expect(pruneExpired(records, 10_000, 1_000)).toEqual([]);
  });

  it('is a no-op (returns the same reference) when nothing expires', () => {
    const records = [record(1_000)];
    expect(pruneExpired(records, 1_000, 5_000)).toBe(records);
  });
});

describe('computeRollingVwap', () => {
  it('computes the volume-weighted average price', () => {
    const records = [
      record(0, { price: 100, size: 2, value: 200 }),
      record(1, { price: 200, size: 1, value: 200 }),
    ];
    expect(computeRollingVwap(records)).toBeCloseTo(133.333, 2);
  });

  it('returns null for an empty window', () => {
    expect(computeRollingVwap([])).toBeNull();
  });
});

describe('computeVwapSet', () => {
  it('reports session VWAP verbatim and derives 1m/5m/15m from the buffer', () => {
    const now = 20 * ONE_MINUTE_MS;
    // Ascending timestamp order — the invariant every caller relies on (trades
    // arrive from the exchange in chronological order).
    const records = [
      record(now - 10 * ONE_MINUTE_MS, { price: 300, size: 1, value: 300 }), // within 15m only
      record(now - 4 * ONE_MINUTE_MS, { price: 200, size: 1, value: 200 }), // within 5m, not 1m
      record(now - 30_000, { price: 100, size: 1, value: 100 }), // within 1m
    ];
    const set = computeVwapSet(records, now, 999);
    expect(set.session).toBe(999);
    expect(set.oneMinute).toBeCloseTo(100);
    expect(set.fiveMinute).toBeCloseTo(150); // (100+200)/2
    expect(set.fifteenMinute).toBeCloseTo(200); // (100+200+300)/3
  });

  it('excludes a record older than 15 minutes even if the buffer still holds it', () => {
    // The rolling buffer is only capacity-bounded, not time-bounded (see
    // TradeAnalyticsEngine) — a stale record past every window must still
    // be excluded at read time, not just "usually already gone."
    const now = 30 * ONE_MINUTE_MS;
    const records = [
      record(now - 20 * ONE_MINUTE_MS, { price: 999, size: 1, value: 999 }), // older than 15m
      record(now - 1_000, { price: 100, size: 1, value: 100 }),
    ];
    const set = computeVwapSet(records, now, null);
    expect(set.fifteenMinute).toBeCloseTo(100);
  });

  it('reports null for a window with no trades yet', () => {
    const set = computeVwapSet([], 0, null);
    expect(set).toEqual({ session: null, oneMinute: null, fiveMinute: null, fifteenMinute: null });
  });
});

describe('computeRollingAnalytics', () => {
  it('counts trades and sums volume within the trailing one minute only', () => {
    const now = ONE_MINUTE_MS * 2;
    const records = [
      record(now - 90_000, { size: 100, side: 'buy' }), // older than 1m — excluded
      record(now - 10_000, { size: 2, side: 'buy' }), // within 1m
    ];
    const analytics = computeRollingAnalytics(records, now);
    expect(analytics.tradesPerMinute).toBe(1);
    expect(analytics.volumePerMinute).toBe(2);
  });

  it('computes average trade size over the one-minute window', () => {
    const now = ONE_MINUTE_MS;
    const records = [record(now - 1_000, { size: 4 }), record(now - 2_000, { size: 2 })];
    expect(computeRollingAnalytics(records, now).avgTradeSize).toBe(3);
  });

  it('tracks the largest trade by value within the window', () => {
    const now = ONE_MINUTE_MS;
    const small = record(now - 1_000, { price: 1, size: 1, value: 1 });
    const large = record(now - 2_000, { price: 1000, size: 1, value: 1000 });
    expect(computeRollingAnalytics([small, large], now).largestTrade).toBe(large);
  });

  it('exposes the raw buy/sell volume that feeds the imbalance figure', () => {
    const now = ONE_MINUTE_MS;
    const records = [
      record(now - 1_000, { side: 'buy', size: 5 }),
      record(now - 1_000, { side: 'sell', size: 2 }),
    ];
    const analytics = computeRollingAnalytics(records, now);
    expect(analytics.buyVolume).toBe(5);
    expect(analytics.sellVolume).toBe(2);
  });

  it('computes buy/sell imbalance bounded to [-1, 1]', () => {
    const now = ONE_MINUTE_MS;
    const allBuys = [record(now - 1_000, { side: 'buy', size: 5 })];
    expect(computeRollingAnalytics(allBuys, now).buySellImbalance).toBe(1);

    const allSells = [record(now - 1_000, { side: 'sell', size: 5 })];
    expect(computeRollingAnalytics(allSells, now).buySellImbalance).toBe(-1);

    const balanced = [
      record(now - 1_000, { side: 'buy', size: 5 }),
      record(now - 1_000, { side: 'sell', size: 5 }),
    ];
    expect(computeRollingAnalytics(balanced, now).buySellImbalance).toBe(0);
  });

  it('reports trades per second over a ten-second window, not a scaled-down minute', () => {
    const now = 10 * ONE_MINUTE_MS;
    const records = [
      record(now - 30_000, { size: 1 }), // within 1m, outside the 10s activity window
      record(now - 5_000, { size: 1 }),
      record(now - 1_000, { size: 1 }),
    ];
    const analytics = computeRollingAnalytics(records, now);
    expect(analytics.tradesPerMinute).toBe(3);
    // Only the two trades inside the last ten seconds count: 2 / 10s = 0.2/s.
    expect(analytics.tradesPerSecond).toBeCloseTo(0.2);
  });

  it('reports null imbalance and average when the window is empty', () => {
    const analytics = computeRollingAnalytics([], ONE_MINUTE_MS);
    expect(analytics.tradesPerMinute).toBe(0);
    expect(analytics.volumePerMinute).toBe(0);
    expect(analytics.tradesPerSecond).toBe(0);
    expect(analytics.buyVolume).toBe(0);
    expect(analytics.sellVolume).toBe(0);
    expect(analytics.avgTradeSize).toBeNull();
    expect(analytics.largestTrade).toBeNull();
    expect(analytics.buySellImbalance).toBeNull();
  });

  it('excludes unknown-side volume from the imbalance calculation', () => {
    const now = ONE_MINUTE_MS;
    const records = [
      record(now - 1_000, { side: 'buy', size: 3 }),
      record(now - 1_000, { side: 'unknown', size: 100 }),
    ];
    // Only the buy volume participates; an all-unknown window would be null, not skewed by it.
    expect(computeRollingAnalytics(records, now).buySellImbalance).toBe(1);
  });

  it('does not require records to be pre-pruned — filters to the last minute itself', () => {
    const now = ONE_MINUTE_MS * 100;
    // Ascending order: the very old record first, the recent one last.
    const records = [record(0, { size: 1000 }), record(now - 1_000, { size: 1 })];
    expect(computeRollingAnalytics(records, now).tradesPerMinute).toBe(1);
  });
});

describe('window size constants', () => {
  it('are in ascending order and match their names', () => {
    expect(ONE_MINUTE_MS).toBe(60_000);
    expect(FIVE_MINUTES_MS).toBe(5 * ONE_MINUTE_MS);
    expect(FIFTEEN_MINUTES_MS).toBe(15 * ONE_MINUTE_MS);
  });
});
