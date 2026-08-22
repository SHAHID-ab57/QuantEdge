'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import { useTheme } from '@mui/material/styles';
import type { CandlestickData, HistogramData } from 'lightweight-charts';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChartContainer } from '@/components/chart';
import { useChartCandles } from '@/components/chart/hooks/use-chart-candles';
import { useSystemHealth, useSystemStatus } from '@/features/health/hooks/use-system-data';
import { useTimeframes } from '@/features/history/hooks/use-history-data';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useNow } from '@/features/markets/hooks/use-now';
import { ConnectionStatus } from './components/connection-status';
import { MarketDataNotice } from './components/market-data-notice';
import { PriceCard } from './components/price-card';
import { TradeTape } from './components/trade-tape';
import { useLiveCandle } from './hooks/use-live-candle';
import { useLiveMarketUrlState } from './hooks/use-live-market-url-state';
import { useMarketStream } from './hooks/use-market-stream';
import { lastCandleTime, usePriceStats } from './hooks/use-price-stats';
import { useResearchMarket } from './hooks/use-research-market';
import { toLiveCandlePoint } from './lib/aggregate-live-candle';
import { readRememberedMarket, rememberMarket } from './lib/remembered-market';
import { resolveTimeframe } from './lib/timeframe-preference';

const MAX_TRADES = 100;

/**
 * The Live Market Dashboard: real-time price, chart, and trade tape for one
 * symbol, driven entirely by the backend's `/api/v1/ws/market` gateway —
 * never by a direct connection to Delta Exchange.
 *
 * Which market is shown is resolved rather than assumed: see
 * `hooks/use-research-market.ts` and `lib/market-selection.ts`. Every widget
 * on the page reads the same resolved `symbol`, and the stream itself
 * discards frames for any other symbol, so the page can never mix two
 * markets together. See `FRONTEND.md` § "Live Market Dashboard".
 */
export function LiveMarketPage() {
  const theme = useTheme();
  const now = useNow();
  const { requestedSymbol, requestedTimeframe, apply } = useLiveMarketUrlState();

  // Read once on mount: local storage is the fallback for a first visit
  // without search params, not a second source of truth to keep in sync.
  const [remembered] = useState(readRememberedMarket);

  const markets = useMarkets();
  const health = useSystemHealth();
  const status = useSystemStatus();
  const research = useResearchMarket(requestedSymbol, remembered.symbol);
  const symbol = research.symbol;

  const timeframesQuery = useTimeframes(symbol);
  const timeframes = useMemo(() => timeframesQuery.data?.timeframes ?? [], [timeframesQuery.data]);

  const [selectedTimeframe, setSelectedTimeframe] = useState<string | null>(null);
  useEffect(() => {
    setSelectedTimeframe(null);
  }, [symbol]);

  const timeframe = useMemo(
    () =>
      resolveTimeframe({
        selected: selectedTimeframe,
        requested: requestedTimeframe,
        remembered: remembered.timeframe,
        available: timeframes,
      }),
    [selectedTimeframe, requestedTimeframe, remembered.timeframe, timeframes],
  );

  // Remember that resolution moved away from an explicitly requested market,
  // so the explanation survives the URL being rewritten to the market that
  // was actually resolved. The functional update keeps this from looping on
  // `research.candidates`, which is a fresh array every render.
  const [fallback, setFallback] = useState<{ from: string; reason: string | null } | null>(null);
  useEffect(() => {
    if (symbol && requestedSymbol && requestedSymbol !== symbol) {
      const readiness = research.candidates.find((entry) => entry.symbol === requestedSymbol);
      const reason = readiness?.blockers[0] ?? null;
      setFallback((previous) =>
        previous?.from === requestedSymbol ? previous : { from: requestedSymbol, reason },
      );
    }
  }, [symbol, requestedSymbol, research.candidates]);

  // Persist the resolved selection. `apply` no-ops when the query string is
  // already correct, so this cannot loop.
  useEffect(() => {
    if (symbol) {
      apply(symbol, timeframe);
      rememberMarket(symbol, timeframe);
    }
  }, [symbol, timeframe, apply]);

  const stream = useMarketStream(symbol, { maxTrades: MAX_TRADES });
  const priceStats = usePriceStats(symbol);

  // Shares a cache entry with the chart's own query (identical key), so
  // reading the last historical candle here costs no extra request.
  const chartCandles = useChartCandles({ symbol, timeframe });
  const seed = useMemo(
    () => toLiveCandlePoint(chartCandles.data?.candles.at(-1)),
    [chartCandles.data],
  );

  const liveCandlePoint = useLiveCandle(stream.latestTrade, timeframe, seed);

  const liveCandle: CandlestickData | null = useMemo(
    () => (liveCandlePoint ? { ...liveCandlePoint } : null),
    [liveCandlePoint],
  );
  const liveVolume: HistogramData | null = useMemo(() => {
    if (!liveCandlePoint) {
      return null;
    }
    return {
      time: liveCandlePoint.time,
      value: liveCandlePoint.volume,
      color:
        liveCandlePoint.close >= liveCandlePoint.open
          ? theme.palette.success.main
          : theme.palette.error.main,
    };
  }, [liveCandlePoint, theme.palette.success.main, theme.palette.error.main]);

  const handleSymbolChange = useCallback(
    (next: string) => {
      // Routed through the URL so the resolver treats it as the requested
      // market; clearing the timeframe lets the new market pick its own.
      setSelectedTimeframe(null);
      setFallback(null);
      apply(next, null);
    },
    [apply],
  );

  const handleRetry = useCallback(() => {
    research.refetch();
    void priceStats.refetch();
    void chartCandles.refetch();
  }, [research, priceStats, chartCandles]);

  const stats = priceStats.data
    ? {
        highestPrice: priceStats.data.highest_price,
        lowestPrice: priceStats.data.lowest_price,
        averageVolume: priceStats.data.average_volume,
        totalCandles: priceStats.data.total_candles,
        lastCandleAt: lastCandleTime(priceStats.data),
      }
    : undefined;

  if (research.isResolving) {
    return (
      <Stack spacing={2} role="status" aria-label="Loading live market dashboard">
        <Skeleton variant="rounded" height={96} />
        <Skeleton variant="rounded" height={140} />
        <Skeleton variant="rounded" height={480} />
      </Stack>
    );
  }

  if (research.isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button size="small" onClick={handleRetry}>
            Retry
          </Button>
        }
      >
        Failed to load markets: {research.error?.message ?? 'the backend is unavailable.'}
      </Alert>
    );
  }

  if (!symbol) {
    return (
      <Alert
        severity="warning"
        role="status"
        action={
          <Button size="small" onClick={handleRetry}>
            Retry
          </Button>
        }
      >
        No market is available to display. The backend returned no active markets.
      </Alert>
    );
  }

  return (
    <Stack spacing={2}>
      <ConnectionStatus
        connectionState={stream.connectionState}
        lastMessageAt={stream.lastMessageAt}
        reconnectAttempt={stream.reconnectAttempt}
        latencyMs={stream.latencyMs}
        health={health.data}
        healthError={health.isError}
        status={status.data}
        now={now}
      />
      {fallback ? (
        <Alert severity="info" role="status" aria-label="Market fallback notice">
          {`${fallback.from} has no research data${
            fallback.reason ? ` (${fallback.reason})` : ''
          } — showing ${symbol} instead.`}
        </Alert>
      ) : null}
      <MarketDataNotice
        symbol={symbol}
        readiness={research.readiness}
        connectionState={stream.connectionState}
        lastMessageAt={stream.lastMessageAt}
        hasPrice={Boolean(stream.latestTicker ?? stream.latestTrade)}
        now={now}
        onRetry={handleRetry}
      />
      <PriceCard
        symbol={symbol}
        latestTrade={stream.latestTrade}
        latestTicker={stream.latestTicker}
        stats={stats}
        statsLoading={priceStats.isLoading}
        statsError={priceStats.isError}
        now={now}
      />
      <ChartContainer
        symbol={symbol}
        timeframe={timeframe}
        markets={markets.data?.markets}
        availableTimeframes={timeframes}
        onSymbolChange={handleSymbolChange}
        onTimeframeChange={setSelectedTimeframe}
        liveCandle={liveCandle}
        liveVolume={liveVolume}
      />
      <TradeTape
        trades={stream.trades}
        isConnecting={stream.connectionState !== 'open'}
        maxTrades={MAX_TRADES}
      />
    </Stack>
  );
}
