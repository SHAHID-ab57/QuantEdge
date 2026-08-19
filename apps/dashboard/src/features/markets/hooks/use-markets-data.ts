'use client';

import { useQuery } from '@tanstack/react-query';
import {
  fetchCandlePage,
  fetchLatestCandle,
  fetchMarkets,
  fetchTimeframes,
} from '@/lib/api/market';

export function useMarkets() {
  return useQuery({
    queryKey: ['markets', 'list'],
    queryFn: fetchMarkets,
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

export function useMarketDetail(symbol: string | null) {
  return useQuery({
    queryKey: ['markets', symbol, 'detail'],
    queryFn: async (): Promise<MarketDetail> => {
      const timeframesResponse = await fetchTimeframes(symbol as string);
      const timeframes = timeframesResponse.timeframes;
      const primaryTimeframe =
        PRIMARY_TIMEFRAME_PREFERENCE.find((tf) => timeframes.includes(tf)) ?? timeframes[0] ?? null;

      const counts = await Promise.all(
        timeframes.slice(0, MAX_TIMEFRAME_COUNTS).map(async (timeframe) => {
          const page = await fetchCandlePage(symbol as string, timeframe, { limit: 1 });
          return { timeframe, count: page.pagination.total };
        }),
      );

      const latest = primaryTimeframe
        ? await fetchLatestCandle(symbol as string, primaryTimeframe)
        : null;

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
    },
    enabled: Boolean(symbol),
    staleTime: 30_000,
  });
}
