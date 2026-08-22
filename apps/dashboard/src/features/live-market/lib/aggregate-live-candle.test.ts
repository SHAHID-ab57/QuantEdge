import type { UTCTimestamp } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import type { Candle } from '@/types/api/market';
import {
  applyTradeToCandle,
  bucketStart,
  timeframeSeconds,
  toLiveCandlePoint,
} from './aggregate-live-candle';

describe('timeframeSeconds', () => {
  it.each([
    ['1m', 60],
    ['5m', 300],
    ['1h', 3600],
    ['4h', 14_400],
    ['1d', 86_400],
  ])('parses %s as %d seconds', (timeframe, expected) => {
    expect(timeframeSeconds(timeframe)).toBe(expected);
  });

  it('returns null for an unrecognized timeframe', () => {
    expect(timeframeSeconds('weekly')).toBeNull();
    expect(timeframeSeconds('')).toBeNull();
  });
});

describe('bucketStart', () => {
  it('floors an epoch second down to the bucket boundary', () => {
    expect(bucketStart(125, 60)).toBe(120);
    expect(bucketStart(3_661, 3_600)).toBe(3_600);
    expect(bucketStart(60, 60)).toBe(60);
  });
});

describe('applyTradeToCandle', () => {
  it('opens a fresh candle at the trade price when there is no prior candle', () => {
    const candle = applyTradeToCandle(null, { price: 100, size: 2, eventTimeSeconds: 65 }, '1m');
    expect(candle).toEqual({ time: 60, open: 100, high: 100, low: 100, close: 100, volume: 2 });
  });

  it('folds a trade in the same bucket into high/low/close/volume', () => {
    const first = applyTradeToCandle(null, { price: 100, size: 2, eventTimeSeconds: 61 }, '1m');
    const second = applyTradeToCandle(first, { price: 105, size: 1, eventTimeSeconds: 62 }, '1m');
    const third = applyTradeToCandle(second, { price: 95, size: 3, eventTimeSeconds: 63 }, '1m');

    expect(third).toEqual({ time: 60, open: 100, high: 105, low: 95, close: 95, volume: 6 });
  });

  it('opens the next bucket at the previous bucket close, not the new trade price', () => {
    const first = applyTradeToCandle(null, { price: 100, size: 1, eventTimeSeconds: 61 }, '1m');
    const second = applyTradeToCandle(first, { price: 110, size: 1, eventTimeSeconds: 125 }, '1m');

    expect(second).toEqual({ time: 120, open: 100, high: 110, low: 100, close: 110, volume: 1 });
  });

  it('returns the current candle unchanged for an unrecognized timeframe', () => {
    const current = { time: 60 as UTCTimestamp, open: 1, high: 1, low: 1, close: 1, volume: 1 };
    expect(applyTradeToCandle(current, { price: 5, size: 1, eventTimeSeconds: 90 }, 'nope')).toBe(
      current,
    );
  });
});

describe('toLiveCandlePoint', () => {
  const candle: Candle = {
    open_time: '2026-01-01T00:00:00Z',
    close_time: '2026-01-01T00:01:00Z',
    open: '100',
    high: '110',
    low: '90',
    close: '105',
    volume: '12.5',
    source: 'delta',
  };

  it('converts a stored candle into a seed for the forming bar', () => {
    expect(toLiveCandlePoint(candle)).toEqual({
      time: Date.parse('2026-01-01T00:00:00Z') / 1000,
      open: 100,
      high: 110,
      low: 90,
      close: 105,
      volume: 12.5,
    });
  });

  it('returns null for a missing candle', () => {
    expect(toLiveCandlePoint(undefined)).toBeNull();
  });

  it('returns null rather than a NaN bar for unparseable values', () => {
    expect(toLiveCandlePoint({ ...candle, high: 'not-a-number' })).toBeNull();
  });

  it('returns null for an unparseable timestamp', () => {
    expect(toLiveCandlePoint({ ...candle, open_time: 'nonsense' })).toBeNull();
  });
});
