import { describe, expect, it } from 'vitest';
import type { TradeRecord } from './trade-record';
import {
  createSessionAccumulator,
  deriveSessionStats,
  foldTradeIntoSession,
  type SessionAccumulator,
} from './session-stats';

function record(overrides: Partial<TradeRecord> = {}): TradeRecord {
  return { price: 100, size: 1, value: 100, side: 'buy', timestampMs: 0, ...overrides };
}

function foldAll(trades: TradeRecord[]): SessionAccumulator {
  return trades.reduce(foldTradeIntoSession, createSessionAccumulator());
}

describe('deriveSessionStats on an empty accumulator', () => {
  it('reports null for every ratio/average, zero for every count', () => {
    const stats = deriveSessionStats(createSessionAccumulator());
    expect(stats).toEqual({
      buyVolume: 0,
      sellVolume: 0,
      totalVolume: 0,
      buySellRatio: null,
      avgTradeSize: null,
      largestTrade: null,
      tradeCount: 0,
      sessionVwap: null,
      avgTradeValue: null,
      lastPrice: null,
      lastSide: null,
      sessionHigh: null,
      sessionLow: null,
    });
  });
});

describe('foldTradeIntoSession', () => {
  it('accumulates buy and sell volume separately', () => {
    const acc = foldAll([
      record({ side: 'buy', size: 3 }),
      record({ side: 'sell', size: 2 }),
      record({ side: 'buy', size: 1 }),
    ]);
    const stats = deriveSessionStats(acc);
    expect(stats.buyVolume).toBe(4);
    expect(stats.sellVolume).toBe(2);
    expect(stats.totalVolume).toBe(6);
    expect(stats.tradeCount).toBe(3);
  });

  it('does not attribute an unknown-side trade to either side, but counts it toward the total', () => {
    const acc = foldAll([record({ side: 'unknown', size: 5 })]);
    const stats = deriveSessionStats(acc);
    expect(stats.buyVolume).toBe(0);
    expect(stats.sellVolume).toBe(0);
    expect(stats.totalVolume).toBe(5);
    expect(stats.tradeCount).toBe(1);
  });

  it('computes buy/sell ratio from cumulative volumes', () => {
    const acc = foldAll([record({ side: 'buy', size: 6 }), record({ side: 'sell', size: 3 })]);
    expect(deriveSessionStats(acc).buySellRatio).toBe(2);
  });

  it('reports a null ratio rather than Infinity when there is no sell volume', () => {
    const acc = foldAll([record({ side: 'buy', size: 6 })]);
    expect(deriveSessionStats(acc).buySellRatio).toBeNull();
  });

  it('computes average trade size as total volume over count', () => {
    const acc = foldAll([record({ size: 2 }), record({ size: 4 }), record({ size: 6 })]);
    expect(deriveSessionStats(acc).avgTradeSize).toBe(4);
  });

  it('tracks the largest trade by notional value, not by size alone', () => {
    const small = record({ price: 1000, size: 1, value: 1000 });
    const large = record({ price: 1, size: 5, value: 5 });
    const acc = foldAll([large, small]);
    expect(deriveSessionStats(acc).largestTrade).toBe(small);
  });

  it('computes session VWAP as cumulative notional over cumulative volume', () => {
    const acc = foldAll([
      record({ price: 100, size: 2, value: 200 }),
      record({ price: 200, size: 1, value: 200 }),
    ]);
    // (200 + 200) / (2 + 1) = 133.33...
    expect(deriveSessionStats(acc).sessionVwap).toBeCloseTo(133.333, 2);
  });

  it('is a pure fold: never mutates the previous accumulator', () => {
    const initial = createSessionAccumulator();
    const next = foldTradeIntoSession(initial, record());
    expect(initial.count).toBe(0);
    expect(next.count).toBe(1);
    expect(initial).not.toBe(next);
  });

  it('tracks the session high and low across every trade, not just recent ones', () => {
    const acc = foldAll([
      record({ price: 100 }),
      record({ price: 130 }),
      record({ price: 90 }),
      record({ price: 110 }),
    ]);
    const stats = deriveSessionStats(acc);
    expect(stats.sessionHigh).toBe(130);
    expect(stats.sessionLow).toBe(90);
  });

  it('reports the most recent trade’s price and side as the current price', () => {
    const acc = foldAll([
      record({ price: 100, side: 'buy' }),
      record({ price: 105, side: 'sell' }),
    ]);
    const stats = deriveSessionStats(acc);
    expect(stats.lastPrice).toBe(105);
    expect(stats.lastSide).toBe('sell');
  });

  it('sets the high and low to the first trade’s price when only one has printed', () => {
    const stats = deriveSessionStats(foldAll([record({ price: 42 })]));
    expect(stats.sessionHigh).toBe(42);
    expect(stats.sessionLow).toBe(42);
  });

  it('computes average trade value (notional) as total notional over count', () => {
    const acc = foldAll([
      record({ price: 100, size: 2, value: 200 }),
      record({ price: 10, size: 1, value: 10 }),
    ]);
    expect(deriveSessionStats(acc).avgTradeValue).toBe(105);
  });
});
