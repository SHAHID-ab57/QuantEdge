'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchCandlePage } from '@/lib/api/market';
import type { Candle } from '@/types/api/market';

/**
 * Matches `candles_max_limit` in `services/api/app/core/config.py` — the
 * largest page the backend will return in one request.
 */
const CHART_PAGE_SIZE = 1000;

/**
 * Upper bound on candles fetched for a single chart render. lightweight-charts
 * itself virtualizes rendering and stays smooth well past this (Objective
 * #8 asks for 10,000+), so the cap exists to bound network/memory cost for
 * a manually-refreshed research chart, not chart rendering performance.
 * Tune here if profiling ever shows it insufficient — see FRONTEND.md.
 */
export const MAX_CHART_CANDLES = 10_000;

export interface ChartCandlesQuery {
  symbol: string | null;
  timeframe: string | null;
  start?: string | null;
  end?: string | null;
}

export interface ChartCandlesResult {
  candles: Candle[];
  total: number;
  /** True when `total` exceeded `MAX_CHART_CANDLES` and older candles were dropped. */
  truncated: boolean;
}

async function fetchChartCandles(
  symbol: string,
  timeframe: string,
  start: string | undefined,
  end: string | undefined,
): Promise<ChartCandlesResult> {
  const shared = { start, end, sort: 'open_time', dir: 'desc' } as const;

  const first = await fetchCandlePage(symbol, timeframe, {
    ...shared,
    limit: CHART_PAGE_SIZE,
    offset: 0,
  });

  const total = first.pagination.total;
  const targetCount = Math.min(total, MAX_CHART_CANDLES);
  const remainingOffsets: number[] = [];
  for (let offset = CHART_PAGE_SIZE; offset < targetCount; offset += CHART_PAGE_SIZE) {
    remainingOffsets.push(offset);
  }

  const restPages =
    remainingOffsets.length > 0
      ? await Promise.all(
          remainingOffsets.map((offset) =>
            fetchCandlePage(symbol, timeframe, { ...shared, limit: CHART_PAGE_SIZE, offset }),
          ),
        )
      : [];

  // Each page is newest-first (dir=desc); pages are requested in ascending
  // offset order, so concatenating them keeps the whole run newest-first.
  // Reverse once at the end to give the chart the ascending order it requires.
  const candles = [first.items, ...restPages.map((page) => page.items)].flat();
  candles.reverse();

  return { candles, total, truncated: total > MAX_CHART_CANDLES };
}

/**
 * Fetches the full OHLCV history a candlestick chart needs for one
 * symbol/timeframe/range, transparently paginating the existing
 * `/markets/{symbol}/candles` endpoint (Objective #10: no duplicate API).
 * When a range holds more than `MAX_CHART_CANDLES` candles, the most recent
 * ones are kept (`truncated: true` is reported so the UI can say so).
 */
export function useChartCandles(query: ChartCandlesQuery) {
  const { symbol, timeframe, start, end } = query;
  return useQuery({
    queryKey: ['chart', 'candles', symbol, timeframe, start, end],
    queryFn: () => fetchChartCandles(symbol!, timeframe!, start ?? undefined, end ?? undefined),
    enabled: Boolean(symbol && timeframe),
  });
}
