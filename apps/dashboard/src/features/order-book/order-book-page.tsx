'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { MarketSelector } from '@/components/chart/market-selector';
import { ConnectionStatus } from '@/features/live-market/components/connection-status';
import {
  useMarketStream,
  type StreamChannels,
} from '@/features/live-market/hooks/use-market-stream';
import { readRememberedMarket, rememberMarket } from '@/features/live-market/lib/remembered-market';
import { useLiveTrackedMarket } from '@/features/live-market/hooks/use-live-tracked-market';
import { useSymbolUrlState } from '@/features/live-market/hooks/use-symbol-url-state';
import { useSystemHealth, useSystemStatus } from '@/features/health/hooks/use-system-data';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useNow } from '@/features/markets/hooks/use-now';
import { DepthSelector } from './components/depth-selector';
import { OrderBookEmptyState } from './components/order-book-empty-state';
import { OrderBookTable } from './components/order-book-table';
import { SpreadPanel } from './components/spread-panel';
import {
  computeDepthRows,
  computeSpread,
  DEFAULT_DEPTH,
  type DepthOption,
} from './lib/order-book-depth';

const EMPTY_LEVELS: never[] = [];

/**
 * This page never reads `latestTrade`/`latestTicker`/`trades` — without
 * this, `useMarketStream` would still fully process every trade and ticker
 * tick (array pushes, new object references) and commit a React state
 * update for each one, re-rendering this whole page on data it throws
 * away. Declared once at module scope so the same stable object is passed
 * every render (`useMarketStream` reads it through a ref, so identity
 * doesn't gate correctness, but a stable reference costs nothing to keep).
 */
const ORDER_BOOK_CHANNELS: StreamChannels = { trades: false, ticker: false, orderBook: true };

/**
 * The Live Order Book Viewer: two synchronized depth tables, a spread
 * summary, and a depth selector for one symbol, driven entirely by the
 * backend's `/api/v1/ws/market` gateway — the same streaming
 * infrastructure the Live Market Dashboard uses, reused via
 * `useMarketStream` rather than opening a second connection type. See
 * `FRONTEND.md` § "Live Order Book Viewer".
 */
export function OrderBookPage() {
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

  const [depth, setDepth] = useState<DepthOption>(DEFAULT_DEPTH);
  const stream = useMarketStream(symbol, { channels: ORDER_BOOK_CHANNELS });

  const handleSymbolChange = useCallback(
    (next: string) => {
      apply(next);
    },
    [apply],
  );

  const handleRetry = useCallback(() => {
    market.refetch();
  }, [market]);

  const book = stream.latestOrderBook;
  const bidLevels = book?.bids ?? EMPTY_LEVELS;
  const askLevels = book?.asks ?? EMPTY_LEVELS;

  const bidRows = useMemo(() => computeDepthRows(bidLevels, depth), [bidLevels, depth]);
  const askRows = useMemo(() => computeDepthRows(askLevels, depth), [askLevels, depth]);
  const spread = useMemo(() => computeSpread(bidLevels, askLevels), [bidLevels, askLevels]);

  const hasBook = book !== null;
  const isBookEmpty = hasBook && bidLevels.length === 0 && askLevels.length === 0;

  if (market.isResolving) {
    return (
      <Stack spacing={2} role="status" aria-label="Loading order book">
        <Skeleton variant="rounded" height={96} />
        <Skeleton variant="rounded" height={64} />
        <Skeleton variant="rounded" height={480} />
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
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        justifyContent="space-between"
      >
        <MarketSelector
          markets={markets.data?.markets ?? []}
          value={symbol}
          onChange={handleSymbolChange}
          loading={markets.isLoading}
        />
        <DepthSelector value={depth} onChange={setDepth} />
      </Stack>
      <OrderBookEmptyState
        symbol={symbol}
        isUntracked={market.isUntracked}
        connectionState={stream.connectionState}
        hasBook={hasBook}
        isBookEmpty={isBookEmpty}
        onRetry={handleRetry}
      />
      <SpreadPanel spread={spread} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <OrderBookTable side="bids" rows={bidRows} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <OrderBookTable side="asks" rows={askRows} />
        </Grid>
      </Grid>
    </Stack>
  );
}
