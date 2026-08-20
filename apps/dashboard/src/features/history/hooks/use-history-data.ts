'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchCandlePage, fetchCandleStats, fetchMarkets, fetchTimeframes } from '@/lib/api/market';

export function useMarkets() {
  return useQuery({
    queryKey: ['history', 'markets'],
    queryFn: fetchMarkets,
  });
}

export function useTimeframes(symbol: string | null) {
  return useQuery({
    queryKey: ['history', 'timeframes', symbol],
    queryFn: () => fetchTimeframes(symbol as string),
    enabled: Boolean(symbol),
  });
}

export interface HistoryQuery {
  symbol: string;
  timeframe: string;
  start: string | null;
  end: string | null;
  limit: number;
}

export interface CandlePageResult {
  page: Awaited<ReturnType<typeof fetchCandlePage>>;
  latencyMs: number;
}

export function useCandles(query: HistoryQuery | null, page: number) {
  return useQuery({
    queryKey: ['history', 'candles', query, page],
    queryFn: async (): Promise<CandlePageResult> => {
      const started = performance.now();
      const result = await fetchCandlePage(query!.symbol, query!.timeframe, {
        limit: query!.limit,
        offset: (page - 1) * query!.limit,
        start: query!.start ?? undefined,
        end: query!.end ?? undefined,
      });
      return { page: result, latencyMs: performance.now() - started };
    },
    enabled: query !== null,
  });
}

export function useCandleStats(query: HistoryQuery | null) {
  return useQuery({
    queryKey: ['history', 'stats', query],
    queryFn: () =>
      fetchCandleStats(query!.symbol, query!.timeframe, {
        start: query!.start ?? undefined,
        end: query!.end ?? undefined,
      }),
    enabled: query !== null,
  });
}
