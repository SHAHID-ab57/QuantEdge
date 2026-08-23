import { describe, expect, it } from 'vitest';
import { ONE_MINUTE_MS } from './rolling-window';
import { computeSizeDistribution } from './size-distribution';
import type { TradeRecord } from './trade-record';

function record(timestampMs: number, size: number): TradeRecord {
  return { price: 100, size, value: 100 * size, side: 'buy', timestampMs };
}

const NOW = 10 * ONE_MINUTE_MS;

describe('computeSizeDistribution', () => {
  it('reports five empty buckets and a null average for an empty window', () => {
    const distribution = computeSizeDistribution([], NOW);
    expect(distribution.total).toBe(0);
    expect(distribution.averageSize).toBeNull();
    expect(distribution.buckets).toHaveLength(5);
    expect(distribution.buckets.every((bucket) => bucket.count === 0 && bucket.share === 0)).toBe(
      true,
    );
  });

  it('excludes trades older than the window', () => {
    const records = [record(NOW - 5 * ONE_MINUTE_MS, 100), record(NOW - 1_000, 1)];
    expect(computeSizeDistribution(records, NOW).total).toBe(1);
  });

  it('places every trade in exactly one bucket', () => {
    const records = [1, 2, 3, 4, 20].map((size, index) => record(NOW - index * 100, size));
    const distribution = computeSizeDistribution(records, NOW);
    const bucketed = distribution.buckets.reduce((sum, bucket) => sum + bucket.count, 0);
    expect(bucketed).toBe(records.length);
    expect(distribution.total).toBe(records.length);
  });

  it('buckets relative to the window average, not an absolute size', () => {
    // Average is 2, so a size-1 trade is 0.5× and a size-3 trade is 1.5×.
    const records = [record(NOW - 200, 1), record(NOW - 100, 3)];
    const distribution = computeSizeDistribution(records, NOW);
    expect(distribution.averageSize).toBe(2);
    expect(distribution.buckets[1]?.label).toBe('0.5–1×');
    expect(distribution.buckets[1]?.count).toBe(1);
    expect(distribution.buckets[2]?.label).toBe('1–2×');
    expect(distribution.buckets[2]?.count).toBe(1);
  });

  it('is scale-invariant — the same shape of flow buckets identically at any magnitude', () => {
    const small = [1, 3].map((size, i) => record(NOW - i * 100, size));
    const large = [1000, 3000].map((size, i) => record(NOW - i * 100, size));
    expect(computeSizeDistribution(small, NOW).buckets.map((b) => b.count)).toEqual(
      computeSizeDistribution(large, NOW).buckets.map((b) => b.count),
    );
  });

  it('puts an outsized print in the open-ended top bucket', () => {
    const records = [
      ...Array.from({ length: 9 }, (_, i) => record(NOW - i * 100, 1)),
      record(NOW - 50, 1000),
    ];
    const distribution = computeSizeDistribution(records, NOW);
    expect(distribution.buckets.at(-1)?.label).toBe('≥5×');
    expect(distribution.buckets.at(-1)?.count).toBe(1);
  });

  it('reports shares that sum to 1 over a non-empty window', () => {
    const records = [1, 2, 5, 10].map((size, i) => record(NOW - i * 100, size));
    const total = computeSizeDistribution(records, NOW).buckets.reduce(
      (sum, bucket) => sum + bucket.share,
      0,
    );
    expect(total).toBeCloseTo(1);
  });

  it('degrades safely (no NaN buckets) when every trade has zero size', () => {
    const records = [record(NOW - 200, 0), record(NOW - 100, 0)];
    const distribution = computeSizeDistribution(records, NOW);
    expect(distribution.total).toBe(2);
    expect(distribution.buckets.every((bucket) => Number.isFinite(bucket.share))).toBe(true);
  });
});
