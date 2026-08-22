'use client';

import { useQueries } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useSystemMetrics } from '@/features/health/hooks/use-system-data';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { fetchTimeframes } from '@/lib/api/market';
import {
  assessMarket,
  buildCandidateSymbols,
  selectResearchMarket,
  type MarketReadiness,
} from '../lib/market-selection';

export interface UseResearchMarketResult {
  /** The resolved market, or `null` while candidates are still being probed. */
  symbol: string | null;
  readiness: MarketReadiness | null;
  /** Readiness for every probed candidate, for diagnostics in the empty state. */
  candidates: MarketReadiness[];
  isResolving: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Resolves which market the dashboard should show, honouring an explicit
 * request (URL) and the remembered selection but never settling on a market
 * with no data behind it — see `lib/market-selection.ts` for the ordering
 * and fallback rules.
 *
 * Candidates are probed with `useQueries` so the (small, capped) set is
 * checked in parallel rather than walked one round-trip at a time, and the
 * query key is the same one `useTimeframes` uses so a probe and the chart's
 * own timeframe fetch share a single cache entry instead of duplicating the
 * request.
 */
export function useResearchMarket(
  requestedSymbol: string | null,
  rememberedSymbol: string | null,
): UseResearchMarketResult {
  const markets = useMarkets();
  const metrics = useSystemMetrics();

  // `/system/metrics` is a live-feed *hint*: if it fails, the dashboard should
  // still resolve a market on historical data alone rather than stall, so its
  // error is deliberately not propagated as a fatal error below.
  const livePrices = metrics.data?.state_latest_prices;

  const candidates = useMemo(
    () =>
      buildCandidateSymbols({
        requested: requestedSymbol,
        remembered: rememberedSymbol,
        markets: markets.data?.markets,
        livePrices,
      }),
    [requestedSymbol, rememberedSymbol, markets.data, livePrices],
  );

  const probes = useQueries({
    queries: candidates.map((symbol) => ({
      queryKey: ['history', 'timeframes', symbol],
      queryFn: () => fetchTimeframes(symbol),
      staleTime: 60_000,
    })),
  });

  // Cheap enough (at most MAX_CANDIDATES entries) to recompute on render;
  // memoizing it would mean deriving a cache key from every probe's status,
  // which is more machinery than the work it would save.
  const readiness = candidates.map((symbol, index) => {
    const probe = probes[index];
    // A failed probe counts as "no candles" rather than staying pending, so a
    // single broken market can never wedge the whole resolution.
    const timeframes = probe?.isError ? [] : probe?.data?.timeframes;
    return assessMarket({ symbol, timeframes, livePrices });
  });

  const selection = selectResearchMarket(readiness);

  const isResolving =
    markets.isLoading || metrics.isLoading || (candidates.length > 0 && selection.isResolving);

  return {
    symbol: selection.symbol,
    readiness: selection.readiness,
    candidates: readiness,
    isResolving,
    isError: markets.isError,
    error: markets.error,
    refetch: () => {
      void markets.refetch();
      void metrics.refetch();
    },
  };
}
