'use client';

import type { CandlestickData, HistogramData } from 'lightweight-charts';
import { useMemo, useRef } from 'react';
import { toChartSeries, type ChartTheme } from '@/components/chart/data-adapter';
import type { Candle } from '@/types/api/market';

export interface ReplayChartSync {
  candlesticks: CandlestickData[];
  volume: HistogramData[];
  liveCandle: CandlestickData | null;
  liveVolume: HistogramData | null;
}

/**
 * Turns replay state into exactly the props `CandlestickChart` already
 * accepts — no new chart implementation, and no change to that component.
 * This mirrors the Live Market Dashboard's own split between a "seeded
 * historical baseline" (`candlesticks`/`volume`, pushed via a full
 * `setData()` only when it changes reference) and "the one bar currently
 * being revealed" (`liveCandle`/`liveVolume`, pushed via `series.update()`)
 * — replay is simply a consumer-paced version of the same mechanism a live
 * feed drives automatically.
 *
 * `revealEpoch` (from `useReplayEngine`) is what decides which path a
 * change takes: it only changes on a discontinuous jump (seek, previous,
 * restart, stop), which is exactly when `lightweight-charts`' `update()`
 * cannot help — it can only append a bar newer than everything already
 * drawn, or replace the single most recent one, never remove history. On
 * an unchanged `revealEpoch`, every `currentIndex` advance is pushed via
 * `liveCandle` alone, so a session can auto-play through thousands of
 * candles without ever calling `setData()` again after the initial seed.
 */
export function useReplayChartSync(
  candles: Candle[],
  currentIndex: number,
  revealEpoch: number,
  theme: ChartTheme,
): ReplayChartSync {
  const seedIndexRef = useRef(-1);

  const historical = useMemo(() => {
    seedIndexRef.current = currentIndex;
    return toChartSeries(candles.slice(0, currentIndex + 1), theme);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deliberately NOT keyed on currentIndex: this must reseed only on a genuine discontinuity (revealEpoch), not on every forward step, or every candle would trigger a full setData(). `theme` is expected to be a stable reference from the caller (memoized on its two color fields), matching `ChartContainer`'s own convention.
  }, [revealEpoch, candles, theme]);

  const live = useMemo(() => {
    if (currentIndex <= seedIndexRef.current) {
      return { liveCandle: null, liveVolume: null };
    }
    const candle = candles[currentIndex];
    if (!candle) {
      return { liveCandle: null, liveVolume: null };
    }
    const series = toChartSeries([candle], theme);
    return {
      liveCandle: series.candlesticks[0] ?? null,
      liveVolume: series.volume[0] ?? null,
    };
  }, [currentIndex, candles, theme]);

  return {
    candlesticks: historical.candlesticks,
    volume: historical.volume,
    liveCandle: live.liveCandle,
    liveVolume: live.liveVolume,
  };
}
