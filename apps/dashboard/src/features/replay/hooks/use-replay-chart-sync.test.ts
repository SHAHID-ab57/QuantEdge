import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Candle } from '@/types/api/market';
import { useReplayChartSync } from './use-replay-chart-sync';

const THEME = { upColor: '#0f0', downColor: '#f00' };

function candle(openTimeIso: string, close = '100'): Candle {
  return {
    open_time: openTimeIso,
    close_time: openTimeIso,
    open: '100',
    high: '100',
    low: '100',
    close,
    volume: '1',
    source: 'test',
  };
}

const CANDLES: Candle[] = Array.from({ length: 5 }, (_, i) =>
  candle(`2026-01-01T00:0${i}:00Z`, String(100 + i)),
);

describe('useReplayChartSync', () => {
  it('seeds historical candlesticks up to and including the current index, with no live candle yet', () => {
    const { result } = renderHook(() => useReplayChartSync(CANDLES, 2, 1, THEME));
    expect(result.current.candlesticks).toHaveLength(3);
    expect(result.current.liveCandle).toBeNull();
  });

  it('pushes the next candle as liveCandle without reseeding historical, on a forward step at the same epoch', () => {
    const { result, rerender } = renderHook(
      ({ index, epoch }: { index: number; epoch: number }) =>
        useReplayChartSync(CANDLES, index, epoch, THEME),
      { initialProps: { index: 2, epoch: 1 } },
    );
    const historicalBefore = result.current.candlesticks;

    rerender({ index: 3, epoch: 1 });

    expect(result.current.candlesticks).toBe(historicalBefore); // same reference — no reseed
    expect(result.current.liveCandle?.close).toBe(103);
  });

  it('reseeds historical (a new reference) when revealEpoch bumps, e.g. a seek or restart', () => {
    const { result, rerender } = renderHook(
      ({ index, epoch }: { index: number; epoch: number }) =>
        useReplayChartSync(CANDLES, index, epoch, THEME),
      { initialProps: { index: 4, epoch: 1 } },
    );
    const historicalBefore = result.current.candlesticks;

    // A restart: back to index 0, epoch bumped.
    rerender({ index: 0, epoch: 2 });

    expect(result.current.candlesticks).not.toBe(historicalBefore);
    expect(result.current.candlesticks).toHaveLength(1);
    expect(result.current.liveCandle).toBeNull();
  });

  it('keeps pushing sequential live candles across several forward steps', () => {
    const { result, rerender } = renderHook(
      ({ index, epoch }: { index: number; epoch: number }) =>
        useReplayChartSync(CANDLES, index, epoch, THEME),
      { initialProps: { index: 0, epoch: 1 } },
    );

    rerender({ index: 1, epoch: 1 });
    expect(result.current.liveCandle?.close).toBe(101);
    rerender({ index: 2, epoch: 1 });
    expect(result.current.liveCandle?.close).toBe(102);
    rerender({ index: 3, epoch: 1 });
    expect(result.current.liveCandle?.close).toBe(103);
  });

  it('recomputes historical when the candle set itself changes (a new session loaded)', () => {
    const { result, rerender } = renderHook(
      ({ candles }: { candles: Candle[] }) => useReplayChartSync(candles, 1, 1, THEME),
      { initialProps: { candles: CANDLES } },
    );
    const before = result.current.candlesticks;

    const newCandles = [candle('2027-01-01T00:00:00Z'), candle('2027-01-01T00:01:00Z')];
    rerender({ candles: newCandles });

    expect(result.current.candlesticks).not.toBe(before);
  });
});
