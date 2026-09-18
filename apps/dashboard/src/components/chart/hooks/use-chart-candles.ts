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

/**
 * How many `/candles` page requests run at once. Real production incident,
 * not a hypothetical: a full 10,000-candle chart load fired all ~9 of its
 * remaining pages via one unbounded `Promise.all`, and on the server's own
 * 2-vCPU box (a single ASGI worker sharing that CPU with the live WebSocket
 * feed and every background scheduler) ten concurrent requests queued badly
 * enough to blow the client's own 10s request timeout — confirmed directly
 * against the live server, not assumed: the identical fetch pattern run
 * sequentially completed each page in well under a second once the backend's
 * own cache warmed (see services/api/app/repositories/candles.py's own
 * _ANALYTICS_CACHE), but ten *concurrent* copies of that same fetch took
 * 25-30s each. Bounding concurrency here trades a slightly slower full
 * chart load for not overwhelming a resource-constrained server — the
 * option chosen deliberately over server-side or backend-architecture
 * changes for this specific bottleneck.
 */
export const MAX_CONCURRENT_PAGE_REQUESTS = 3;

export interface ChartCandlesQuery {
  symbol: string | null;
  timeframe: string | null;
  start?: string | null;
  end?: string | null;
  /**
   * When set, the historical candles are refetched on this interval (ms) so
   * bars that closed since the page loaded pick up their authoritative
   * backend values, rather than being left as the client-synthesized
   * approximation the forming-bar logic produced. The Live Market Dashboard
   * passes this; a manually-refreshed research chart (History) omits it and
   * fetches once. Not part of the query key — a caller that shares this
   * symbol/timeframe/range without an interval still benefits from the
   * refetched data via the shared cache entry.
   */
  refetchIntervalMs?: number;
}

export interface ChartCandlesResult {
  candles: Candle[];
  total: number;
  /** True when `total` exceeded `MAX_CHART_CANDLES` and older candles were dropped. */
  truncated: boolean;
}

/**
 * Runs `fetch(item)` for every `items` entry with at most `concurrency` calls
 * in flight at once, returning results in the same order as `items` —
 * matches `Promise.all`'s own ordering contract, just bounded. A fixed pool
 * of `concurrency` lanes each pulls the next unclaimed index and awaits its
 * own fetch before pulling again, rather than batching in fixed-size groups,
 * so a lane that finishes early immediately picks up the next item instead
 * of waiting for the slowest item in its batch.
 */
async function fetchPagesWithBoundedConcurrency<T>(
  items: number[],
  fetch: (item: number) => Promise<T>,
  concurrency: number,
): Promise<T[]> {
  const results: T[] = [];
  const queue = items.map((item, index) => ({ item, index }));

  async function lane(): Promise<void> {
    let next = queue.shift();
    while (next !== undefined) {
      results[next.index] = await fetch(next.item);
      next = queue.shift();
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, lane));
  return results;
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

  const restPages = await fetchPagesWithBoundedConcurrency(
    remainingOffsets,
    (offset) => fetchCandlePage(symbol, timeframe, { ...shared, limit: CHART_PAGE_SIZE, offset }),
    MAX_CONCURRENT_PAGE_REQUESTS,
  );

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
  const { symbol, timeframe, start, end, refetchIntervalMs } = query;
  return useQuery({
    queryKey: ['chart', 'candles', symbol, timeframe, start, end],
    queryFn: () => fetchChartCandles(symbol!, timeframe!, start ?? undefined, end ?? undefined),
    enabled: Boolean(symbol && timeframe),
    refetchInterval: refetchIntervalMs ?? false,
  });
}
