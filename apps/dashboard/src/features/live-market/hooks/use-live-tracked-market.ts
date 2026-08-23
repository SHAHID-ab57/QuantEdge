'use client';

import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useSystemMetrics } from '@/features/health/hooks/use-system-data';
import { buildCandidateSymbols } from '../lib/market-selection';

export interface UseLiveTrackedMarketResult {
  symbol: string | null;
  /** True if a symbol was resolved but it isn't actually on the live feed. */
  isUntracked: boolean;
  isResolving: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Resolves which market a live-feed-only page should show — originally
 * built for the Order Book viewer and promoted here once the Live Trade
 * Analytics dashboard needed the exact same rule, to avoid a third
 * copy-paste of it.
 *
 * Readiness here is exactly one thing: is the backend actually streaming
 * this symbol? (`state_latest_prices` from `/system/metrics` is a reliable
 * proxy — every symbol in `DELTA_MARKET_SYMBOLS` is subscribed to the same
 * set of live channels — trades, ticker, and order-book — together, see
 * `app/runtime.py`'s `LIVE_CHANNELS`.) This is deliberately *not* the same
 * as the Live Market Dashboard's own resolver (`useResearchMarket`), which
 * additionally requires stored candles — a page whose entire feature set
 * comes from the live stream (order book depth, trade analytics) has no
 * use for that check, and forcing it would gate an otherwise-ready market
 * on an irrelevant historical-candle requirement. `buildCandidateSymbols`
 * (URL → remembered → `ETHUSD` → live-tracked → any active) is the one
 * piece both resolvers genuinely share, so it's reused here as-is.
 *
 * An explicitly *requested* symbol (present in the URL right now) is always
 * honoured verbatim, even if it turns out to be untracked — `isUntracked`
 * tells the caller's own empty-state component to explain why, rather than
 * the page silently substituting a different market than the one the user
 * asked for. A merely *remembered* symbol (left over from a previous visit,
 * not an active request) gets no such guarantee: if it's no longer
 * tracked, resolution prefers a live-tracked candidate instead, since
 * reopening the page to the same broken state every time would be
 * unfriendly.
 */
export function useLiveTrackedMarket(
  requestedSymbol: string | null,
  rememberedSymbol: string | null,
): UseLiveTrackedMarketResult {
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
    // No per-candidate async probe needed (no candle-timeframes fetch) —
    // everything this depends on is already in `markets`/`metrics`, so
    // "resolving" is exactly "still loading".
    isResolving: markets.isLoading || metrics.isLoading,
    isError: markets.isError,
    error: markets.error,
    refetch: () => {
      void markets.refetch();
      void metrics.refetch();
    },
  };
}
