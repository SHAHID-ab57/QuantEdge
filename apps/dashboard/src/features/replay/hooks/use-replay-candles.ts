'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchAllCandles } from '@/lib/api/paginate-candles';
import type { Candle } from '@/types/api/market';

/** A hard ceiling on session size — generous headroom over 24h of 1-minute candles (1,440), while still protecting the browser from an accidental all-history query. */
export const MAX_REPLAY_CANDLES = 20_000;

export const REPLAY_PAGE_LIMIT = 1_000;

export interface ReplaySessionConfig {
  symbol: string;
  timeframe: string;
  /** ISO-8601, inclusive. */
  start: string;
  /** ISO-8601, exclusive. */
  end: string;
}

export interface ReplayCandlesResult {
  candles: Candle[];
  /** `true` if the session was cut off by `MAX_REPLAY_CANDLES` before the range was fully loaded. */
  truncated: boolean;
}

/** A stable string identity for one configuration, used both as the TanStack Query key and as `useReplayEngine`'s `requestId`. */
export function replayConfigKey(config: ReplaySessionConfig): string {
  return `${config.symbol}|${config.timeframe}|${config.start}|${config.end}`;
}

async function loadReplaySession(config: ReplaySessionConfig): Promise<ReplayCandlesResult> {
  const { candles, truncated } = await fetchAllCandles(
    {
      symbol: config.symbol,
      timeframe: config.timeframe,
      start: config.start,
      end: config.end,
      limit: REPLAY_PAGE_LIMIT,
      sort: 'open_time',
      dir: 'asc',
    },
    undefined,
    Math.ceil(MAX_REPLAY_CANDLES / REPLAY_PAGE_LIMIT),
  );
  return { candles, truncated: truncated || candles.length > MAX_REPLAY_CANDLES };
}

/**
 * Loads an entire replay session's candles up front — every candle between
 * `start` and `end`, paginated via `fetchAllCandles` (shared with the
 * History page's export) — so playback can step through an in-memory array
 * with no further network round-trip per candle. `MAX_REPLAY_CANDLES`
 * exists because a researcher picking "all history" at a 1-minute
 * timeframe would otherwise try to load millions of candles into the
 * browser; `truncated` tells the UI to say so rather than silently
 * replaying a shorter session than requested.
 */
export function useReplayCandles(config: ReplaySessionConfig | null) {
  return useQuery({
    queryKey: ['replay', 'candles', config ? replayConfigKey(config) : null],
    queryFn: () => loadReplaySession(config as ReplaySessionConfig),
    enabled: config !== null,
    staleTime: Infinity,
    retry: 1,
  });
}
