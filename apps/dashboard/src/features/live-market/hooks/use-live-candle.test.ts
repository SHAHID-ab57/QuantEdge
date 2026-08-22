import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { UTCTimestamp } from 'lightweight-charts';
import type { LiveTradeData } from '@/types/api/market-stream';
import { useLiveCandle } from './use-live-candle';

function trade(price: string, eventTime: string): LiveTradeData {
  return { price, size: '1', side: 'unknown', event_time: eventTime };
}

describe('useLiveCandle', () => {
  it('returns null until the first trade arrives', () => {
    const { result } = renderHook(() => useLiveCandle(null, '1m'));
    expect(result.current).toBeNull();
  });

  it('builds a candle from the first trade', () => {
    const { result, rerender } = renderHook(
      ({ latestTrade, timeframe }) => useLiveCandle(latestTrade, timeframe),
      { initialProps: { latestTrade: null as LiveTradeData | null, timeframe: '1m' } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:00:05Z'), timeframe: '1m' });
    expect(result.current).toMatchObject({ open: 100, high: 100, low: 100, close: 100, volume: 1 });
  });

  it('folds subsequent trades in the same bucket', () => {
    const { result, rerender } = renderHook(
      ({ latestTrade, timeframe }) => useLiveCandle(latestTrade, timeframe),
      { initialProps: { latestTrade: null as LiveTradeData | null, timeframe: '1m' } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:00:05Z'), timeframe: '1m' });
    rerender({ latestTrade: trade('105', '2026-01-01T00:00:30Z'), timeframe: '1m' });

    expect(result.current).toMatchObject({ open: 100, high: 105, low: 100, close: 105, volume: 2 });
  });

  it('discards the old bucket and re-derives a fresh candle at the new timeframe', () => {
    const { result, rerender } = renderHook(
      ({ latestTrade, timeframe }) => useLiveCandle(latestTrade, timeframe),
      { initialProps: { latestTrade: null as LiveTradeData | null, timeframe: '1m' } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:00:05Z'), timeframe: '1m' });
    rerender({ latestTrade: trade('105', '2026-01-01T00:00:30Z'), timeframe: '1m' });
    expect(result.current).toMatchObject({ open: 100, close: 105 });

    // Switching timeframe re-derives from the last known trade alone —
    // it does not carry over the previous timeframe's open/high/low.
    rerender({ latestTrade: trade('105', '2026-01-01T00:00:30Z'), timeframe: '5m' });
    expect(result.current).toMatchObject({ open: 105, high: 105, low: 105, close: 105, volume: 1 });
  });

  it('stays null after a timeframe change when no trade has arrived yet', () => {
    const { result, rerender } = renderHook(
      ({ latestTrade, timeframe }) => useLiveCandle(latestTrade, timeframe),
      { initialProps: { latestTrade: null as LiveTradeData | null, timeframe: '1m' } },
    );

    rerender({ latestTrade: null, timeframe: '5m' });
    expect(result.current).toBeNull();
  });

  it('ignores a trade with an unparseable event_time', () => {
    const { result, rerender } = renderHook(
      ({ latestTrade, timeframe }) => useLiveCandle(latestTrade, timeframe),
      { initialProps: { latestTrade: null as LiveTradeData | null, timeframe: '1m' } },
    );

    rerender({
      latestTrade: { price: '100', size: '1', side: 'unknown', event_time: 'not-a-date' },
      timeframe: '1m',
    });

    expect(result.current).toBeNull();
  });

  it('extends the seeded historical bar when a trade lands in its bucket', () => {
    const seed = {
      time: (Date.parse('2026-01-01T00:00:00Z') / 1000) as UTCTimestamp,
      open: 90,
      high: 95,
      low: 88,
      close: 92,
      volume: 5,
    };
    const { result, rerender } = renderHook(
      ({ latestTrade }) => useLiveCandle(latestTrade, '1m', seed),
      { initialProps: { latestTrade: null as LiveTradeData | null } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:00:30Z') });

    // Same bucket as the seed: the historical bar continues rather than a
    // fresh one-trade bar replacing it at the same timestamp.
    expect(result.current).toMatchObject({
      time: seed.time,
      open: 90,
      high: 100,
      low: 88,
      close: 100,
      volume: 6,
    });
  });

  it('opens a new bar at the seed close when the trade is in a later bucket', () => {
    const seed = {
      time: (Date.parse('2026-01-01T00:00:00Z') / 1000) as UTCTimestamp,
      open: 90,
      high: 95,
      low: 88,
      close: 92,
      volume: 5,
    };
    const { result, rerender } = renderHook(
      ({ latestTrade }) => useLiveCandle(latestTrade, '1m', seed),
      { initialProps: { latestTrade: null as LiveTradeData | null } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:01:30Z') });

    expect(result.current).toMatchObject({
      time: (Date.parse('2026-01-01T00:01:00Z') / 1000) as UTCTimestamp,
      open: 92, // continuity with the previous close, no gap
      close: 100,
      volume: 1,
    });
  });

  it('adopts a newer synced historical bar over the locally-formed one', () => {
    const early = {
      time: (Date.parse('2026-01-01T00:00:00Z') / 1000) as UTCTimestamp,
      open: 90,
      high: 95,
      low: 88,
      close: 92,
      volume: 5,
    };
    const synced = { ...early, time: (Date.parse('2026-01-01T00:01:00Z') / 1000) as UTCTimestamp };

    const { result, rerender } = renderHook(
      ({ latestTrade, seed }) => useLiveCandle(latestTrade, '1m', seed),
      { initialProps: { latestTrade: null as LiveTradeData | null, seed: early } },
    );

    rerender({ latestTrade: trade('100', '2026-01-01T00:00:30Z'), seed: early });
    expect(result.current?.time).toBe(early.time);

    // Candle sync catches up and the newer bar supersedes the synthesized one.
    rerender({ latestTrade: trade('101', '2026-01-01T00:01:30Z'), seed: synced });
    expect(result.current?.time).toBe(synced.time);
  });
});
