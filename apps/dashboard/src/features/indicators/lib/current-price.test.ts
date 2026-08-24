import { describe, expect, it } from 'vitest';
import type { Candle } from '@/types/api/market';
import { extractCurrentPrice } from './current-price';

function candle(overrides: Partial<Candle> = {}): Candle {
  return {
    open_time: '2026-01-01T00:00:00Z',
    close_time: '2026-01-01T01:00:00Z',
    open: '100',
    high: '110',
    low: '90',
    close: '105',
    volume: '1000',
    source: 'delta',
    ...overrides,
  };
}

describe('extractCurrentPrice', () => {
  it('reads the field matching the resolved source parameter', () => {
    expect(extractCurrentPrice(candle(), 'high')).toBe(110);
    expect(extractCurrentPrice(candle(), 'low')).toBe(90);
    expect(extractCurrentPrice(candle(), 'open')).toBe(100);
  });

  it('defaults to close for an indicator with no source parameter', () => {
    expect(extractCurrentPrice(candle(), undefined)).toBe(105);
  });

  it('defaults to close for an unrecognized source value', () => {
    expect(extractCurrentPrice(candle(), 'vwap')).toBe(105);
  });

  it('defaults to close when the source is not a string at all', () => {
    expect(extractCurrentPrice(candle(), 42)).toBe(105);
  });
});
