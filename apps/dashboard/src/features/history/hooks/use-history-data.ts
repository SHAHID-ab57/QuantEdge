'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchCandlePage, fetchMarkets, fetchTimeframes } from '@/lib/api/market';

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

export const HISTORY_LIMIT_OPTIONS = [100, 250, 500, 1000] as const;

export const CANDLE_SORT_COLUMNS = ['open_time', 'open', 'high', 'low', 'close', 'volume'] as const;

export type CandleSortColumn = (typeof CANDLE_SORT_COLUMNS)[number];
export type CandleSortDirection = 'asc' | 'desc';

export interface HistoryQuery {
  symbol: string;
  timeframe: string;
  start: string | null;
  end: string | null;
  limit: number;
  sort: CandleSortColumn;
  dir: CandleSortDirection;
}

export function useCandles(query: HistoryQuery | null, page: number) {
  return useQuery({
    queryKey: ['history', 'candles', query, page],
    queryFn: () =>
      fetchCandlePage(query!.symbol, query!.timeframe, {
        limit: query!.limit,
        offset: (page - 1) * query!.limit,
        start: query!.start ?? undefined,
        end: query!.end ?? undefined,
        sort: query!.sort,
        dir: query!.dir,
      }),
    enabled: query !== null,
  });
}
