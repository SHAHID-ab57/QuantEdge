'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Skeleton from '@mui/material/Skeleton';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { MarketSelector } from '@/components/chart/market-selector';
import { Section } from '@/components/section';
import { ConnectionStatus } from '@/features/live-market/components/connection-status';
import { TradeTape } from '@/features/live-market/components/trade-tape';
import { useLiveTrackedMarket } from '@/features/live-market/hooks/use-live-tracked-market';
import { useSymbolUrlState } from '@/features/live-market/hooks/use-symbol-url-state';
import { readRememberedMarket, rememberMarket } from '@/features/live-market/lib/remembered-market';
import { useSystemHealth, useSystemStatus } from '@/features/health/hooks/use-system-data';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useNow } from '@/features/markets/hooks/use-now';
import { LargestTradeCard } from './components/largest-trade-card';
import { MarketSentimentPanel } from './components/market-sentiment-panel';
import { MetricInfo } from './components/metric-info';
import {
  MaxRowsSelector,
  DEFAULT_MAX_ROWS,
  type MaxRowsOption,
} from './components/max-rows-selector';
import { PriceHeader } from './components/price-header';
import { RollingAnalyticsPanel } from './components/rolling-analytics-panel';
import { StatsCards } from './components/stats-cards';
import { TapeExportButton } from './components/tape-export-button';
import { TradeAnalyticsEmptyState } from './components/trade-analytics-empty-state';
import { TradeSizeDistribution } from './components/trade-size-distribution';
import { TradeTapeFilters, type TradeSideFilter } from './components/trade-tape-filters';
import { VwapPanel } from './components/vwap-panel';
import { useTradeAnalytics } from './hooks/use-trade-analytics';
import { LARGE_TRADE_MULTIPLIER } from './lib/trade-highlight';

/**
 * The Live Trade Analytics dashboard: a live trade tape, session/rolling
 * statistics, VWAP, sparkline trends, and a market-sentiment summary for
 * one symbol, driven entirely by the backend's `/api/v1/ws/market` gateway
 * via `useTradeAnalytics` (itself a thin adapter over `useMarketStream` and
 * a `TradeAnalyticsEngine` — see `engine/trade-analytics-engine.ts`). This
 * component only lays out already-computed state; it performs no
 * calculation of its own beyond the display-only tape filters below, which
 * intentionally never touch the underlying accumulators.
 *
 * Information hierarchy, in descending visual weight:
 *
 * 1. `PriceHeader` — current price, session range, VWAP distance, live
 *    activity. The entry point; everything below is a step down in weight.
 * 2. `Section`s grouping related metrics — Order Flow, VWAP & Trends,
 *    Session Statistics, Trade Tape — each one bordered surface with its
 *    heading built in, rather than the previous flat run of same-weight
 *    panels separated by rules.
 *
 * See `FRONTEND.md` § "Live Trade Analytics Dashboard".
 */
export function TradesPage() {
  const now = useNow();
  const { requestedSymbol, apply } = useSymbolUrlState();
  const [remembered] = useState(readRememberedMarket);

  const markets = useMarkets();
  const health = useSystemHealth();
  const status = useSystemStatus();
  const market = useLiveTrackedMarket(requestedSymbol, remembered.symbol);
  const symbol = market.symbol;

  useEffect(() => {
    if (symbol) {
      apply(symbol);
      rememberMarket(symbol, null);
    }
  }, [symbol, apply]);

  const [maxRows, setMaxRows] = useState<MaxRowsOption>(DEFAULT_MAX_ROWS);
  const [sideFilter, setSideFilter] = useState<TradeSideFilter>('all');
  const [minSize, setMinSize] = useState(0);
  const analytics = useTradeAnalytics(symbol, { maxTapeRows: maxRows });

  const handleSymbolChange = useCallback(
    (next: string) => {
      apply(next);
    },
    [apply],
  );

  const handleRetry = useCallback(() => {
    market.refetch();
  }, [market]);

  const largeTradeThreshold =
    analytics.sessionStats.avgTradeValue !== null
      ? analytics.sessionStats.avgTradeValue * LARGE_TRADE_MULTIPLIER
      : undefined;

  const filteredTrades = useMemo(() => {
    if (sideFilter === 'all' && minSize <= 0) {
      // Nothing to filter — hand back the same array reference so the
      // memoized `TradeTape` can skip re-rendering entirely.
      return analytics.trades;
    }
    return analytics.trades.filter((trade) => {
      if (sideFilter !== 'all' && trade.side !== sideFilter) {
        return false;
      }
      if (minSize > 0) {
        const size = Number(trade.size);
        if (!Number.isFinite(size) || size < minSize) {
          return false;
        }
      }
      return true;
    });
  }, [analytics.trades, sideFilter, minSize]);

  if (market.isResolving) {
    return (
      <Stack spacing={2} role="status" aria-label="Loading trade analytics">
        <Skeleton variant="rounded" height={104} />
        <Skeleton variant="rounded" height={64} />
        <Skeleton variant="rounded" height={140} />
        <Skeleton variant="rounded" height={440} />
      </Stack>
    );
  }

  if (market.isError) {
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
        Failed to load markets: {market.error?.message ?? 'the backend is unavailable.'}
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
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        justifyContent="space-between"
      >
        <MarketSelector
          markets={markets.data?.markets ?? []}
          value={symbol}
          onChange={handleSymbolChange}
          loading={markets.isLoading}
        />
        <MaxRowsSelector value={maxRows} onChange={setMaxRows} />
      </Stack>

      <PriceHeader
        symbol={symbol}
        stats={analytics.sessionStats}
        vwapDistance={analytics.vwapDistance}
        tradesPerSecond={analytics.rolling.tradesPerSecond}
        isLive={analytics.connectionState === 'open'}
      />

      <TradeAnalyticsEmptyState
        symbol={symbol}
        isUntracked={market.isUntracked}
        connectionState={analytics.connectionState}
        hasAnyTrade={analytics.sessionStats.tradeCount > 0}
        onRetry={handleRetry}
      />

      <Section title="Order Flow" subtitle="Trailing one minute">
        <Stack spacing={2}>
          <MarketSentimentPanel sentiment={analytics.sentiment} rolling={analytics.rolling} />
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="flex-start">
            <RollingAnalyticsPanel rolling={analytics.rolling} history={analytics.history} />
            <TradeSizeDistribution distribution={analytics.sizeDistribution} />
          </Stack>
        </Stack>
      </Section>

      <Section title="VWAP" subtitle="Volume-weighted average price, session and rolling windows">
        <VwapPanel vwap={analytics.vwap} history={analytics.history} />
      </Section>

      <Section title="Session Statistics" subtitle="Since this page connected to the symbol">
        <Stack spacing={2}>
          <StatsCards stats={analytics.sessionStats} />
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <LargestTradeCard
              title="Largest Trade — Session"
              trade={analytics.sessionStats.largestTrade}
            />
            <LargestTradeCard
              title="Largest Trade — Last Minute"
              trade={analytics.rolling.largestTrade}
            />
          </Stack>
        </Stack>
      </Section>

      <Section title="Connection" subtitle="Live stream and backend health">
        <ConnectionStatus
          connectionState={analytics.connectionState}
          lastMessageAt={analytics.lastMessageAt}
          reconnectAttempt={analytics.reconnectAttempt}
          latencyMs={analytics.latencyMs}
          health={health.data}
          healthError={health.isError}
          status={status.data}
          now={now}
        />
      </Section>

      <TradeTapeFilters
        side={sideFilter}
        onSideChange={setSideFilter}
        minSize={minSize}
        onMinSizeChange={setMinSize}
        visibleCount={filteredTrades.length}
        totalCount={analytics.trades.length}
        action={
          <TapeExportButton
            trades={filteredTrades}
            symbol={symbol}
            sideFilter={sideFilter}
            minSize={minSize}
          />
        }
      />
      <TradeTape
        trades={filteredTrades}
        isConnecting={analytics.connectionState !== 'open'}
        maxTrades={maxRows}
        showTradeValue
        largeTradeThreshold={largeTradeThreshold}
        virtualize
        valueColumnInfo={<MetricInfo metric="tradeValue" label="Trade Value" />}
      />
    </Stack>
  );
}
