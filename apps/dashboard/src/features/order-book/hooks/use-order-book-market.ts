'use client';

import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useSystemMetrics } from '@/features/health/hooks/use-system-data';
import { buildCandidateSymbols } from '@/features/live-market/lib/market-selection';

export interface UseOrderBookMarketResult {
  symbol: string | null;
  /** True if a symbol was resolved but it isn't actually on the live feed. */
  isUntracked: boolean;
  isResolving: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Resolves which market the order book viewer should show.
 *
 * An order book has no notion of "stored candles" — unlike the Live Market
 * Dashboard, readiness here is exactly one thing: is the backend actually
 * streaming this symbol's order book? (`state_latest_prices` from
 * `/system/metrics` is a reliable proxy — every symbol in
 * `DELTA_MARKET_SYMBOLS` is subscribed to the same set of live channels,
 * trades/ticker/order-book together, see `app/runtime.py`'s
 * `LIVE_CHANNELS`.) So this hook reuses the Live Market Dashboard's
 * candidate-ordering policy (`buildCandidateSymbols` — URL → remembered →
 * `ETHUSD` → live-tracked → any active) but *not* its candle-aware
 * readiness/fallback machinery (`assessMarket`/`selectResearchMarket`),
 * which would be the wrong tool here: forcing that reuse would gate an
 * order-book-ready market on an irrelevant historical-candle check.
 *
 * An explicitly *requested* symbol (present in the URL right now) is always
 * honoured verbatim, even if it turns out to be untracked — `isUntracked`
 * tells `OrderBookEmptyState` to explain why, rather than the page silently
 * substituting a different market than the one the user asked for. A merely
 * *remembered* symbol (left over from a previous visit, not an active
 * request) gets no such guarantee: if it's no longer tracked, resolution
 * prefers a live-tracked candidate instead, since reopening the page to the
 * same broken state every time would be unfriendly.
 */
export function useOrderBookMarket(
  requestedSymbol: string | null,
  rememberedSymbol: string | null,
): UseOrderBookMarketResult {
  const markets = useMarkets();
  const metrics = useSystemMetrics();
  const livePrices = metrics.data?.state_latest_prices;

  const candidates = buildCandidateSymbols({
    requested: requestedSymbol,
    remembered: rememberedSymbol,
    markets: markets.data?.markets,
    livePrices,
  });

  const liveTracked = new Set(Object.keys(livePrices ?? {}));
  const requestedIsValid = requestedSymbol !== null && candidates[0] === requestedSymbol;
  const symbol = requestedIsValid
    ? requestedSymbol
    : (candidates.find((candidate) => liveTracked.has(candidate)) ?? candidates[0] ?? null);

  return {
    symbol,
    isUntracked: symbol !== null && !liveTracked.has(symbol),
    // Unlike the Live Market Dashboard, readiness here needs no per-candidate
    // async probe (no candle-timeframes fetch) — everything it depends on is
    // already in `markets`/`metrics`, so "resolving" is exactly "still loading".
    isResolving: markets.isLoading || metrics.isLoading,
    isError: markets.isError,
    error: markets.error,
    refetch: () => {
      void markets.refetch();
      void metrics.refetch();
    },
  };
}
