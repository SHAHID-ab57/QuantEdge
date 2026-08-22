import { describe, expect, it } from 'vitest';
import type { OrderBookLevelData } from '@/types/api/market-stream';
import { computeDepthRows, computeSpread } from './order-book-depth';

function level(price: string, size: string): OrderBookLevelData {
  return { price, size };
}

describe('computeDepthRows', () => {
  it('computes a running cumulative total from best price outward', () => {
    const rows = computeDepthRows([level('100', '1'), level('99', '2'), level('98', '3')], 10);
    expect(rows.map((row) => row.total)).toEqual([1, 3, 6]);
  });

  it('scales depthRatio against the deepest row in the slice, not the whole book', () => {
    const rows = computeDepthRows([level('100', '1'), level('99', '1'), level('98', '2')], 2);
    // Sliced to 2 rows before computing totals, so the deepest visible row is 2, not 4.
    expect(rows).toHaveLength(2);
    expect(rows[0]!.depthRatio).toBeCloseTo(0.5);
    expect(rows[1]!.depthRatio).toBeCloseTo(1);
  });

  it('never exceeds the requested depth', () => {
    const levels = Array.from({ length: 150 }, (_, i) => level(String(1000 - i), '1'));
    expect(computeDepthRows(levels, 100)).toHaveLength(100);
    expect(computeDepthRows(levels, 10)).toHaveLength(10);
  });

  it('returns an empty array for an empty book side, not a crash', () => {
    expect(computeDepthRows([], 25)).toEqual([]);
  });

  it('treats an unparseable level as zero rather than propagating NaN', () => {
    const rows = computeDepthRows([level('not-a-number', 'also-not-a-number')], 10);
    expect(rows[0]).toMatchObject({ price: 0, size: 0, total: 0, depthRatio: 0 });
  });

  it('handles a 100+ level book without truncation artifacts', () => {
    const levels = Array.from({ length: 120 }, (_, i) => level(String(1000 - i), '1'));
    const rows = computeDepthRows(levels, 100);
    expect(rows).toHaveLength(100);
    expect(rows[0]!.total).toBe(1);
    expect(rows[99]!.total).toBe(100);
    expect(rows[99]!.depthRatio).toBeCloseTo(1);
  });
});

describe('computeSpread', () => {
  it('computes best bid/ask, spread, spread percent, and mid price', () => {
    const summary = computeSpread([level('100', '1')], [level('101', '1')]);
    expect(summary.bestBid).toBe(100);
    expect(summary.bestAsk).toBe(101);
    expect(summary.spread).toBe(1);
    expect(summary.midPrice).toBe(100.5);
    expect(summary.spreadPercent).toBeCloseTo((1 / 100.5) * 100);
  });

  it('reports every field as null when the bid side is empty', () => {
    const summary = computeSpread([], [level('101', '1')]);
    expect(summary).toEqual({
      bestBid: null,
      bestAsk: 101,
      spread: null,
      spreadPercent: null,
      midPrice: null,
    });
  });

  it('reports every field as null when the ask side is empty', () => {
    const summary = computeSpread([level('100', '1')], []);
    expect(summary.spread).toBeNull();
    expect(summary.midPrice).toBeNull();
  });

  it('reports every field as null when both sides are empty', () => {
    const summary = computeSpread([], []);
    expect(summary.bestBid).toBeNull();
    expect(summary.bestAsk).toBeNull();
  });

  it('only reads the best (first) level of each side', () => {
    const summary = computeSpread(
      [level('100', '1'), level('50', '99')],
      [level('101', '1'), level('200', '99')],
    );
    expect(summary.bestBid).toBe(100);
    expect(summary.bestAsk).toBe(101);
  });
});
