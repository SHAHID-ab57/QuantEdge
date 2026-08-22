'use client';

import { useEffect, useRef, useState } from 'react';
import type { LiveTradeData } from '@/types/api/market-stream';
import { applyTradeToCandle, type LiveCandlePoint } from '../lib/aggregate-live-candle';

/**
 * Tracks the currently-forming candle for `timeframe`, folding in each new
 * `latestTrade` as it arrives.
 *
 * `seed` is the last *historical* candle (from the chart's REST data). It
 * matters for continuity in two ways: a trade landing inside the seed's own
 * bucket extends that bar rather than starting a fresh one-trade bar at the
 * same timestamp, and a trade in a later bucket opens at the seed's close
 * rather than gapping. It is also how the forming bar recovers after the
 * candle-sync job catches up: once a *newer* historical bar exists, it
 * supersedes the locally-synthesized one.
 *
 * Resets whenever `timeframe` changes — a different bucket size needs a
 * fresh forming bar, not one computed at the previous resolution.
 */
export function useLiveCandle(
  latestTrade: LiveTradeData | null,
  timeframe: string | null,
  seed: LiveCandlePoint | null = null,
): LiveCandlePoint | null {
  const [candle, setCandle] = useState<LiveCandlePoint | null>(null);

  // Read through a ref so a historical refetch (which produces a new `seed`
  // object every time) never re-runs the fold and double-counts a trade.
  const seedRef = useRef(seed);
  seedRef.current = seed;

  useEffect(() => {
    setCandle(null);
  }, [timeframe]);

  useEffect(() => {
    if (!latestTrade || !timeframe) {
      return;
    }
    const eventTimeSeconds = Math.floor(Date.parse(latestTrade.event_time) / 1000);
    if (!Number.isFinite(eventTimeSeconds)) {
      return;
    }
    setCandle((current) => {
      const currentSeed = seedRef.current;
      const base =
        current === null || (currentSeed !== null && currentSeed.time > current.time)
          ? currentSeed
          : current;
      return applyTradeToCandle(
        base,
        { price: Number(latestTrade.price), size: Number(latestTrade.size), eventTimeSeconds },
        timeframe,
      );
    });
  }, [latestTrade, timeframe]);

  return candle;
}
