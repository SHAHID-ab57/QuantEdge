import { describe, expect, it } from 'vitest';
import { computeColumnStats, isNumericDtype } from './column-stats';

describe('computeColumnStats', () => {
  it('computes min, max, mean, and std over numeric values', () => {
    const stats = computeColumnStats([1, 2, 3, 4, 5]);
    expect(stats.min).toBe(1);
    expect(stats.max).toBe(5);
    expect(stats.mean).toBe(3);
    expect(stats.std).toBeCloseTo(Math.sqrt(2), 5);
    expect(stats.nullCount).toBe(0);
    expect(stats.count).toBe(5);
  });

  it('counts nulls separately and excludes them from the numeric stats', () => {
    const stats = computeColumnStats([1, null, 3, null]);
    expect(stats.nullCount).toBe(2);
    expect(stats.min).toBe(1);
    expect(stats.max).toBe(3);
    expect(stats.count).toBe(4);
  });

  it('excludes non-numeric cells (strings, booleans) from the numeric stats', () => {
    const stats = computeColumnStats(['up', 'down', true, 2]);
    expect(stats.min).toBe(2);
    expect(stats.max).toBe(2);
    expect(stats.nullCount).toBe(0);
  });

  it('returns all-null stats when there are no numeric values at all', () => {
    const stats = computeColumnStats(['up', 'down']);
    expect(stats.min).toBeNull();
    expect(stats.max).toBeNull();
    expect(stats.mean).toBeNull();
    expect(stats.std).toBeNull();
  });

  it('returns a zero standard deviation for a single repeated value', () => {
    const stats = computeColumnStats([5, 5, 5]);
    expect(stats.std).toBe(0);
  });
});

describe('isNumericDtype', () => {
  it('treats float and int as numeric', () => {
    expect(isNumericDtype('float')).toBe(true);
    expect(isNumericDtype('int')).toBe(true);
  });

  it('treats categorical and other dtypes as non-numeric', () => {
    expect(isNumericDtype('categorical')).toBe(false);
    expect(isNumericDtype('bool')).toBe(false);
  });
});
