import { describe, expect, it } from 'vitest';
import {
  MAX_RECENT_CALCULATIONS,
  RECENT_CALCULATIONS_KEY,
  readRecentCalculations,
  withRecentCalculation,
  writeRecentCalculations,
  type RecentCalculation,
} from './recent-calculations';

function entry(overrides: Partial<RecentCalculation> = {}): RecentCalculation {
  return {
    symbol: 'ETHUSD',
    indicator: 'sma',
    indicatorLabel: 'Simple Moving Average',
    timeframe: '1h',
    params: { period: '20' },
    timestamp: 1,
    ...overrides,
  };
}

function fakeStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value);
    },
    removeItem: (key) => {
      data.delete(key);
    },
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  } as Storage;
}

describe('withRecentCalculation', () => {
  it('prepends a new entry', () => {
    const result = withRecentCalculation([], entry());
    expect(result).toEqual([entry()]);
  });

  it('moves an identical configuration to the top instead of duplicating it', () => {
    const first = entry({ timestamp: 1 });
    const rerun = entry({ timestamp: 2 });
    const result = withRecentCalculation([first], rerun);
    expect(result).toEqual([rerun]);
  });

  it('treats a different parameter set as a distinct entry', () => {
    const first = entry({ params: { period: '20' } });
    const second = entry({ params: { period: '50' } });
    const result = withRecentCalculation([first], second);
    expect(result).toEqual([second, first]);
  });

  it('caps the list at the maximum length', () => {
    const existing = Array.from({ length: MAX_RECENT_CALCULATIONS }, (_, i) =>
      entry({ symbol: `M${i}`, timestamp: i }),
    );
    const result = withRecentCalculation(existing, entry({ symbol: 'NEW', timestamp: 999 }));
    expect(result).toHaveLength(MAX_RECENT_CALCULATIONS);
    expect(result[0]?.symbol).toBe('NEW');
  });
});

describe('readRecentCalculations / writeRecentCalculations', () => {
  it('round-trips through storage', () => {
    const storage = fakeStorage();
    writeRecentCalculations(storage, [entry()]);
    expect(readRecentCalculations(storage)).toEqual([entry()]);
  });

  it('returns an empty list when nothing is stored', () => {
    expect(readRecentCalculations(fakeStorage())).toEqual([]);
  });

  it('returns an empty list rather than throwing on corrupted JSON', () => {
    const storage = fakeStorage();
    storage.setItem(RECENT_CALCULATIONS_KEY, '{not json');
    expect(readRecentCalculations(storage)).toEqual([]);
  });

  it('returns an empty list when the stored value is not an array', () => {
    const storage = fakeStorage();
    storage.setItem(RECENT_CALCULATIONS_KEY, JSON.stringify({ not: 'an array' }));
    expect(readRecentCalculations(storage)).toEqual([]);
  });

  it('does not throw when storage.getItem throws (private browsing)', () => {
    const throwing = {
      getItem: () => {
        throw new Error('blocked');
      },
    } as unknown as Storage;
    expect(() => readRecentCalculations(throwing)).not.toThrow();
    expect(readRecentCalculations(throwing)).toEqual([]);
  });

  it('does not throw when storage.setItem throws (quota exceeded)', () => {
    const throwing = {
      setItem: () => {
        throw new Error('quota');
      },
    } as unknown as Storage;
    expect(() => writeRecentCalculations(throwing, [entry()])).not.toThrow();
  });
});
