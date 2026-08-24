'use client';

import { useTheme } from '@mui/material/styles';
import { useMemo, useRef } from 'react';
import { resolveOverlayColor } from '@/components/chart/overlay-colors';
import { createOverlaySeriesCache } from '../lib/overlay-series';
import { useOverlayCalculations } from './use-overlay-calculations';
import { useOverlayStore } from '../store/use-overlay-store';

export interface UseChartOverlaysInput {
  symbol: string | null;
  timeframe: string | null;
  start?: string;
  end?: string;
  limit?: number;
}

/**
 * The single hook a chart-bearing page needs: reads the session's overlay
 * configuration from `useOverlayStore`, calculates every enabled one via
 * the batch API, and returns chart-ready `OverlaySeriesInput[]` plus the
 * raw store state a panel/legend needs. One call wires a page into the
 * whole Indicator Management & Chart Overlay System.
 *
 * `overlaySeries` (the full per-overlay result — success/error and
 * calculation metadata included) is kept separate from `chartOverlays`
 * (the trimmed `{id, label, color, data}` shape `CandlestickChart` wants):
 * the chart should never re-render just because an unrelated `meta` field
 * changed, so the two are memoized independently.
 */
export function useChartOverlays({ symbol, timeframe, start, end, limit }: UseChartOverlaysInput) {
  const theme = useTheme();
  const overlays = useOverlayStore((state) => state.overlays);
  const calculation = useOverlayCalculations({ symbol, timeframe, start, end, limit, overlays });

  // One memoizing cache per mounted chart — see `createOverlaySeriesCache`
  // for why this is what lets an untouched overlay's chart line skip a
  // redraw even though the whole batch response is a new object every
  // fetch (TanStack Query's structural sharing keeps an unchanged result's
  // reference stable; this cache is what turns that into a stable `data`
  // reference per overlay on top of it).
  const cacheRef = useRef<ReturnType<typeof createOverlaySeriesCache> | null>(null);
  cacheRef.current ??= createOverlaySeriesCache();

  const overlaySeries = useMemo(
    () =>
      cacheRef.current!(calculation.data, overlays, (overlay) =>
        resolveOverlayColor(theme, overlay.colorIndex, overlay.colorOverride),
      ),
    [calculation.data, overlays, theme],
  );

  const chartOverlays = useMemo(
    () => overlaySeries.map(({ id, label, color, data }) => ({ id, label, color, data })),
    [overlaySeries],
  );

  return {
    overlays,
    overlaySeries,
    chartOverlays,
    isLoading: calculation.isLoading,
    isError: calculation.isError,
    error: calculation.error,
  };
}
