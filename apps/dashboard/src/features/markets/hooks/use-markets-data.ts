'use client';

import { useQuery, type QueryClient } from '@tanstack/react-query';
import {
  fetchCandlePage,
  fetchLatestCandle,
  fetchMarketResearch,
  fetchMarkets,
  fetchTimeframes,
} from '@/lib/api/market';
import type { ResearchTimeframeMetrics } from '@/types/api/market';

export function useMarkets() {
  return useQuery({
    queryKey: ['markets', 'list'],
    queryFn: fetchMarkets,
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });
}

const PRIMARY_TIMEFRAME_PREFERENCE = ['1h', '4h', '1d', '15m', '30m', '5m', '1m'];
const MAX_TIMEFRAME_COUNTS = 8;

export interface MarketDetail {
  timeframes: string[];
  primaryTimeframe: string | null;
  latestPrice: string | null;
  latestCandleTime: string | null;
  candleCounts: Array<{ timeframe: string; count: number }>;
  totalCandles: number;
  lastSyncAt: string | null;
}

export async function fetchMarketDetail(symbol: string): Promise<MarketDetail> {
  const timeframesResponse = await fetchTimeframes(symbol);
  const timeframes = timeframesResponse.timeframes;
  const primaryTimeframe =
    PRIMARY_TIMEFRAME_PREFERENCE.find((tf) => timeframes.includes(tf)) ?? timeframes[0] ?? null;

  const counts = await Promise.all(
    timeframes.slice(0, MAX_TIMEFRAME_COUNTS).map(async (timeframe) => {
      const page = await fetchCandlePage(symbol, timeframe, { limit: 1 });
      return { timeframe, count: page.pagination.total };
    }),
  );

  const latest = primaryTimeframe ? await fetchLatestCandle(symbol, primaryTimeframe) : null;

  const totalCandles = counts.reduce((sum, entry) => sum + entry.count, 0);
  return {
    timeframes,
    primaryTimeframe,
    latestPrice: latest ? latest.candle.close : null,
    latestCandleTime: latest ? latest.candle.close_time : null,
    candleCounts: counts,
    totalCandles,
    lastSyncAt: latest ? latest.candle.close_time : null,
  };
}

export const marketDetailQueryKey = (symbol: string | null) =>
  ['markets', symbol, 'detail'] as const;

export function prefetchMarketDetail(client: QueryClient, symbol: string) {
  const key = marketDetailQueryKey(symbol);
  if (client.getQueryState(key)) {
    return;
  }
  void client.prefetchQuery({
    queryKey: key,
    queryFn: () => fetchMarketDetail(symbol),
    staleTime: 30_000,
  });
}

export function useMarketDetail(symbol: string | null) {
  return useQuery({
    queryKey: marketDetailQueryKey(symbol),
    queryFn: () => fetchMarketDetail(symbol as string),
    enabled: Boolean(symbol),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

export function useMarketResearch(symbol: string | null) {
  return useQuery({
    queryKey: ['markets', symbol, 'research'],
    queryFn: () => fetchMarketResearch(symbol as string),
    enabled: Boolean(symbol),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

export function useTimeframeResearch(
  symbol: string | null,
  timeframe: string | null,
): ResearchTimeframeMetrics | null | undefined {
  const research = useMarketResearch(symbol);
  if (research.data === undefined || timeframe === null) {
    return undefined;
  }
  return research.data.timeframes.find((entry) => entry.timeframe === timeframe) ?? null;
}
