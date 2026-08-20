import type { z } from 'zod';
import { apiClient } from './client';
import {
  CandlePageSchema,
  CandleStatsSchema,
  LatestCandleSchema,
  MarketListSchema,
  TimeframesSchema,
  type CandlePage,
  type CandleStats,
  type LatestCandle,
  type MarketList,
  type Timeframes,
} from '@/types/api/market';

async function getValidated<T>(path: string, schema: z.ZodType<T>, query?: string): Promise<T> {
  const { data } = await apiClient.get(query ? `${path}?${query}` : path);
  return schema.parse(data);
}

export function fetchMarkets(): Promise<MarketList> {
  return getValidated('/api/v1/markets', MarketListSchema);
}

export function fetchTimeframes(symbol: string): Promise<Timeframes> {
  return getValidated(`/api/v1/markets/${encodeURIComponent(symbol)}/timeframes`, TimeframesSchema);
}

export function fetchLatestCandle(symbol: string, timeframe: string): Promise<LatestCandle> {
  return getValidated(
    `/api/v1/markets/${encodeURIComponent(symbol)}/latest`,
    LatestCandleSchema,
    `timeframe=${encodeURIComponent(timeframe)}`,
  );
}

export function fetchCandlePage(
  symbol: string,
  timeframe: string,
  params: { limit?: number; offset?: number; start?: string; end?: string } = {},
): Promise<CandlePage> {
  const search = new URLSearchParams({ timeframe });
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  if (params.start) search.set('start', params.start);
  if (params.end) search.set('end', params.end);
  return getValidated(
    `/api/v1/markets/${encodeURIComponent(symbol)}/candles`,
    CandlePageSchema,
    search.toString(),
  );
}

export function fetchCandleStats(
  symbol: string,
  timeframe: string,
  params: { start?: string; end?: string } = {},
): Promise<CandleStats> {
  const search = new URLSearchParams({ timeframe });
  if (params.start) search.set('start', params.start);
  if (params.end) search.set('end', params.end);
  return getValidated(
    `/api/v1/markets/${encodeURIComponent(symbol)}/candles/stats`,
    CandleStatsSchema,
    search.toString(),
  );
}
