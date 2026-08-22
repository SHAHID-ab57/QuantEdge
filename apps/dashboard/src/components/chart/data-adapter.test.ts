import { describe, expect, it } from 'vitest';
import type { Candle } from '@/types/api/market';
import { toChartSeries, toUnixTime } from './data-adapter';

const THEME = { upColor: '#22c55e', downColor: '#ef4444' };

function candle(overrides: Partial<Candle> = {}): Candle {
  return {
    open_time: '2026-08-01T00:00:00Z',
    close_time: '2026-08-01T01:00:00Z',
    open: '3000',
    high: '3100',
    low: '2950',
    close: '3055.25',
    volume: '120.5',
    source: 'delta',
    ...overrides,
  };
}

describe('toUnixTime', () => {
  it('converts an ISO timestamp to whole UTC seconds', () => {
    expect(toUnixTime('2026-08-01T00:00:00Z')).toBe(
      Math.floor(Date.parse('2026-08-01T00:00:00Z') / 1000),
    );
  });

  it('returns null for an unparseable timestamp', () => {
    expect(toUnixTime('not-a-date')).toBeNull();
  });
});

describe('toChartSeries', () => {
  it('converts candles into ascending candlestick and volume points', () => {
    const result = toChartSeries(
      [
        candle({ open_time: '2026-08-01T01:00:00Z', open: '3055.25', close: '3180.5' }),
        candle({ open_time: '2026-08-01T00:00:00Z' }),
      ],
      THEME,
    );

    expect(result.skipped).toBe(0);
    expect(result.candlesticks).toHaveLength(2);
    expect(result.candlesticks.map((point) => point.time)).toEqual([
      toUnixTime('2026-08-01T00:00:00Z'),
      toUnixTime('2026-08-01T01:00:00Z'),
    ]);
    expect(result.candlesticks[0]).toMatchObject({
      open: 3000,
      high: 3100,
      low: 2950,
      close: 3055.25,
    });
    expect(result.volume).toHaveLength(2);
    expect(result.volume[0]).toMatchObject({ value: 120.5 });
  });

  it('colors a bullish candle with upColor and a bearish candle with downColor', () => {
    const result = toChartSeries(
      [
        candle({ open_time: '2026-08-01T00:00:00Z', open: '100', close: '110' }),
        candle({ open_time: '2026-08-01T01:00:00Z', open: '110', close: '90' }),
      ],
      THEME,
    );
    expect(result.volume[0]?.color).toBe(THEME.upColor);
    expect(result.volume[1]?.color).toBe(THEME.downColor);
  });

  it('skips a candle with an unparseable timestamp', () => {
    const result = toChartSeries([candle({ open_time: 'not-a-date' })], THEME);
    expect(result.candlesticks).toHaveLength(0);
    expect(result.skipped).toBe(1);
  });

  it('skips a candle with a non-numeric OHLCV field', () => {
    const result = toChartSeries([candle({ close: 'not-a-number' })], THEME);
    expect(result.candlesticks).toHaveLength(0);
    expect(result.skipped).toBe(1);
  });

  it('skips a duplicate timestamp instead of overwriting the first candle', () => {
    const result = toChartSeries([candle({ close: '3055.25' }), candle({ close: '9999' })], THEME);
    expect(result.candlesticks).toHaveLength(1);
    expect(result.candlesticks[0]?.close).toBe(3055.25);
    expect(result.skipped).toBe(1);
  });

  it('handles a large dataset without dropping valid candles', () => {
    const candles: Candle[] = Array.from({ length: 10_000 }, (_, index) =>
      candle({
        open_time: new Date(Date.UTC(2020, 0, 1) + index * 60_000).toISOString(),
        close_time: new Date(Date.UTC(2020, 0, 1) + (index + 1) * 60_000).toISOString(),
      }),
    );
    const result = toChartSeries(candles, THEME);
    expect(result.candlesticks).toHaveLength(10_000);
    expect(result.skipped).toBe(0);
    for (let index = 1; index < result.candlesticks.length; index += 1) {
      expect(Number(result.candlesticks[index]!.time)).toBeGreaterThan(
        Number(result.candlesticks[index - 1]!.time),
      );
    }
  });
});
