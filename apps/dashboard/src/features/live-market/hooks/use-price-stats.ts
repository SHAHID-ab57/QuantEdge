'use client';

import { useQuery } from '@tanstack/react-query';
import { toIsoUtc } from '@/features/history/lib/resolve-range';
import { fetchCandleStats } from '@/lib/api/market';

/** Fixed granularity for the rolling 24h window, independent of the chart's own timeframe. */
const STATS_TIMEFRAME = '5m';
const DAY_MS = 86_400_000;
const REFRESH_INTERVAL_MS = 60_000;

/**
 * Polls the existing `/candles/stats` REST endpoint for a rolling 24h
 * window — no new backend endpoint needed. 24h high/low/volume don't
 * need push-level freshness the way current price does, so a 60s poll
 * (the same pattern the Health page already uses at 10s) is enough; only
 * the live WebSocket stream needs to be push-based.
 */
export function usePriceStats(symbol: string | null) {
  return useQuery({
    queryKey: ['live-market', 'price-stats', symbol],
    queryFn: () => {
      const now = new Date();
      const start = new Date(now.getTime() - DAY_MS);
      return fetchCandleStats(symbol as string, STATS_TIMEFRAME, {
        start: toIsoUtc(start),
        end: toIsoUtc(now),
      });
    },
    enabled: Boolean(symbol),
    refetchInterval: REFRESH_INTERVAL_MS,
  });
}

/** Open time of the newest stored candle in the window, or `null` if the window is empty. */
export function lastCandleTime(stats: {
  last_candle: { open_time: string } | null;
}): string | null {
  return stats.last_candle?.open_time ?? null;
}

/** Total 24h volume derived from the endpoint's per-candle average (sum = average × count). */
export function total24hVolume(averageVolume: string | null, totalCandles: number): number | null {
  if (averageVolume === null || totalCandles === 0) {
    return null;
  }
  const parsed = Number(averageVolume);
  return Number.isFinite(parsed) ? parsed * totalCandles : null;
}
