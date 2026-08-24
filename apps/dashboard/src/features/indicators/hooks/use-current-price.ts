'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchLatestCandle } from '@/lib/api/market';

/**
 * The market's most recent stored price, reused from the existing
 * `GET /markets/{symbol}/latest` endpoint (already built for the History
 * page) rather than adding raw price data to the indicator calculation
 * response — the indicator API's job is indicator values, not candles it
 * already exposes elsewhere.
 */
export function useCurrentPrice(symbol: string | null, timeframe: string) {
  return useQuery({
    queryKey: ['indicators', 'current-price', symbol, timeframe],
    queryFn: () => fetchLatestCandle(symbol!, timeframe),
    enabled: Boolean(symbol && timeframe),
    staleTime: 30_000,
  });
}
