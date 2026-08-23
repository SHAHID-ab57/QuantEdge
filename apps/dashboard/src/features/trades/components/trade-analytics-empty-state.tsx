'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import { memo } from 'react';
import type { ConnectionState } from '@/features/live-market/hooks/use-market-stream';

export interface TradeAnalyticsEmptyStateProps {
  symbol: string;
  isUntracked: boolean;
  connectionState: ConnectionState;
  hasAnyTrade: boolean;
  onRetry: () => void;
}

function connectionDetail(connectionState: ConnectionState): string {
  if (connectionState === 'open') {
    return 'Connected; no trade has printed yet for this market.';
  }
  if (connectionState === 'reconnecting') {
    return 'The live stream dropped and is reconnecting automatically.';
  }
  return 'The live stream is not connected yet.';
}

/**
 * Explains why the tape/statistics are still empty, mirroring the Order
 * Book viewer's `OrderBookEmptyState` in shape (same untracked/connection
 * cases) but with trade-specific copy — the two components aren't merged
 * since their messages genuinely differ (an order book vs. a trade
 * stream), matching the same judgment call made for that component.
 *
 * Renders nothing once at least one trade has been seen, so a healthy,
 * actively-trading view carries no notice.
 */
function TradeAnalyticsEmptyStateInner({
  symbol,
  isUntracked,
  connectionState,
  hasAnyTrade,
  onRetry,
}: TradeAnalyticsEmptyStateProps) {
  if (hasAnyTrade) {
    return null;
  }

  if (isUntracked) {
    return (
      <Alert
        severity="warning"
        role="status"
        aria-label={`Trade analytics availability for ${symbol}`}
        action={
          <Button size="small" onClick={onRetry}>
            Retry
          </Button>
        }
      >
        <AlertTitle>{symbol} is not on the live feed</AlertTitle>
        This market receives no streaming trades, so no analytics can be computed.
      </Alert>
    );
  }

  const title =
    connectionState === 'reconnecting'
      ? `Reconnecting to the ${symbol} trade stream`
      : `Waiting for the first ${symbol} trade`;

  return (
    <Alert
      severity="info"
      role="status"
      aria-label={`Trade analytics availability for ${symbol}`}
      action={
        <Button size="small" onClick={onRetry}>
          Retry
        </Button>
      }
    >
      <AlertTitle>{title}</AlertTitle>
      {connectionDetail(connectionState)} Quiet markets can go minutes between trades.
    </Alert>
  );
}

export const TradeAnalyticsEmptyState = memo(TradeAnalyticsEmptyStateInner);
