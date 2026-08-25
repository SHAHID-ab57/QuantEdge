import { describe, expect, it } from 'vitest';
import { toDatasetRange } from './resolve-dataset-range';

describe('toDatasetRange', () => {
  it('returns no bounds for "all"', () => {
    expect(toDatasetRange({ range: 'all', start: '', end: '' })).toEqual({
      start: undefined,
      end: undefined,
    });
  });

  it('resolves a named preset via resolveRange', () => {
    const result = toDatasetRange({ range: '7d', start: '', end: '' });
    expect(result.start).toEqual(expect.any(String));
    expect(result.end).toEqual(expect.any(String));
  });

  it('builds a half-open range from custom start/end dates', () => {
    const result = toDatasetRange({ range: 'custom', start: '2026-01-01', end: '2026-01-02' });
    expect(result.start).toBe('2026-01-01T00:00:00Z');
    // The end day is included in full: it becomes the *start* of the next day.
    expect(result.end).toBe('2026-01-03T00:00:00Z');
  });

  it('returns no bounds for a custom range missing either date', () => {
    expect(toDatasetRange({ range: 'custom', start: '', end: '2026-01-02' })).toEqual({});
    expect(toDatasetRange({ range: 'custom', start: '2026-01-01', end: '' })).toEqual({});
  });
});
