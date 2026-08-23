'use client';

import { useCallback, useMemo, useRef } from 'react';
import { useNow } from '@/features/markets/hooks/use-now';
import {
  useMarketStream,
  type ConnectionState,
  type StreamChannels,
} from '@/features/live-market/hooks/use-market-stream';
import type { LiveTradeData } from '@/types/api/market-stream';
import {
  TradeAnalyticsEngine,
  type TradeAnalyticsSnapshot,
} from '../engine/trade-analytics-engine';

export const DEFAULT_MAX_TAPE_ROWS = 100;

/**
 * This page only ever reads trade prints — never ticker or order-book
 * data — so both other channels are disabled the same way the Order Book
 * viewer disables trades/ticker: dropped by `useMarketStream` before they
 * touch a buffer or schedule a commit, at zero cost to this page.
 */
const TRADE_ANALYTICS_CHANNELS: StreamChannels = { trades: true, ticker: false, orderBook: false };

/** How often the wall clock re-triggers a recompute even with no new trade — see below. */
const CLOCK_TICK_MS = 1_000;

export interface UseTradeAnalyticsOptions {
  /** Display cap for the trade tape only — analytics accuracy never depends on this. */
  maxTapeRows?: number;
  /** Overridable for tests; defaults to deriving from `NEXT_PUBLIC_API_URL`. */
  streamUrl?: string;
}

export interface UseTradeAnalyticsResult extends TradeAnalyticsSnapshot {
  connectionState: ConnectionState;
  lastMessageAt: number | null;
  reconnectAttempt: number;
  latencyMs: number | null;
  /** Newest first, capped at `maxTapeRows` — for the trade tape only. */
  trades: LiveTradeData[];
}

/**
 * Drives the Live Trade Analytics dashboard: one `useMarketStream`
 * connection (trades-only), plus a `TradeAnalyticsEngine`
 * (`engine/trade-analytics-engine.ts`) that owns every accumulator and
 * calculation. This hook is deliberately thin — it does not fold trades or
 * compute a single statistic itself; it only (a) feeds every trade to the
 * engine via `onTrade`, exactly once, before `useMarketStream`'s own rAF
 * batching or `maxTrades` display cap can lose any of them, and (b) asks
 * the engine for a fresh snapshot whenever React has a reason to recompute.
 * Components consume that snapshot's already-derived state — they never
 * see a raw accumulator or call a calculation function directly.
 *
 * The engine lives in a `useRef` (survives across renders, one instance per
 * mounted hook) and is discarded and rebuilt on a symbol change, the same
 * "this state belongs to a different identity now" pattern used elsewhere
 * in this codebase, so a market switch can never blend one symbol's trades
 * into another's stats.
 *
 * The snapshot is recomputed via `useMemo` keyed on `stream.lastTradeAt` (a
 * new trade actually arrived) *and* a 1-second wall clock tick (`useNow`) —
 * the second dependency is what lets the rolling window and sparklines
 * visibly age out during a quiet market instead of showing stale data
 * frozen at whenever the last trade printed.
 */
export function useTradeAnalytics(
  symbol: string | null,
  options: UseTradeAnalyticsOptions = {},
): UseTradeAnalyticsResult {
  const engineRef = useRef(new TradeAnalyticsEngine());

  const symbolRef = useRef(symbol);
  if (symbolRef.current !== symbol) {
    symbolRef.current = symbol;
    engineRef.current.reset();
  }

  const handleTrade = useCallback((trade: LiveTradeData) => {
    engineRef.current.ingest(trade);
  }, []);

  const stream = useMarketStream(symbol, {
    maxTrades: options.maxTapeRows ?? DEFAULT_MAX_TAPE_ROWS,
    channels: TRADE_ANALYTICS_CHANNELS,
    onTrade: handleTrade,
    streamUrl: options.streamUrl,
  });

  const now = useNow(CLOCK_TICK_MS);

  const snapshot = useMemo(
    () => engineRef.current.snapshot(now),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- engineRef.current is read fresh; now/lastTradeAt/symbol are the real triggers.
    [now, stream.lastTradeAt, symbol],
  );

  return {
    connectionState: stream.connectionState,
    lastMessageAt: stream.lastMessageAt,
    reconnectAttempt: stream.reconnectAttempt,
    latencyMs: stream.latencyMs,
    trades: stream.trades,
    ...snapshot,
  };
}
