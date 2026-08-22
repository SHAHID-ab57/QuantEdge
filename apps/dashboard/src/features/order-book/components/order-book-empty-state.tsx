'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import { memo } from 'react';
import type { ConnectionState } from '@/features/live-market/hooks/use-market-stream';

export interface OrderBookEmptyStateProps {
  symbol: string;
  isUntracked: boolean;
  connectionState: ConnectionState;
  /** Whether a book (even an empty one) has been reconstructed at all yet. */
  hasBook: boolean;
  /** True when a book exists but both sides are empty. */
  isBookEmpty: boolean;
  onRetry: () => void;
}

function connectionDetail(connectionState: ConnectionState): string {
  if (connectionState === 'open') {
    return 'Connected; the first snapshot has not arrived yet.';
  }
  if (connectionState === 'reconnecting') {
    return 'The live stream dropped and is reconnecting automatically.';
  }
  return 'The live stream is not connected yet.';
}

/**
 * Explains why the depth tables aren't showing data, distinguishing the
 * cases that need different fixes: the market isn't on the live feed at
 * all, the stream hasn't delivered a snapshot yet (and whether that's
 * because it's still disconnected or just quiet), versus a genuinely empty
 * book (both sides empty — a valid, if unusual, reconstructed state).
 *
 * Renders nothing once a non-empty book exists, so a healthy view carries
 * no notice.
 */
function OrderBookEmptyStateInner({
  symbol,
  isUntracked,
  connectionState,
  hasBook,
  isBookEmpty,
  onRetry,
}: OrderBookEmptyStateProps) {
  if (hasBook && !isBookEmpty) {
    return null;
  }

  if (isUntracked) {
    return (
      <Alert
        severity="warning"
        role="status"
        aria-label={`Order book availability for ${symbol}`}
        action={
          <Button size="small" onClick={onRetry}>
            Retry
          </Button>
        }
      >
        <AlertTitle>{symbol} is not on the live feed</AlertTitle>
        This market has no order book depth, so it receives no streaming updates.
      </Alert>
    );
  }

  if (isBookEmpty) {
    return (
      <Alert severity="info" role="status" aria-label={`Order book availability for ${symbol}`}>
        <AlertTitle>The order book for {symbol} is empty</AlertTitle>
        The backend has reconstructed a book with no levels on either side. This can happen briefly
        around a resync — it should populate on the next update.
      </Alert>
    );
  }

  const title =
    connectionState === 'reconnecting'
      ? `Reconnecting to the ${symbol} order book`
      : `Waiting for the ${symbol} order book`;
  const detail = connectionDetail(connectionState);

  return (
    <Alert
      severity="info"
      role="status"
      aria-label={`Order book availability for ${symbol}`}
      action={
        <Button size="small" onClick={onRetry}>
          Retry
        </Button>
      }
    >
      <AlertTitle>{title}</AlertTitle>
      {detail}
    </Alert>
  );
}

export const OrderBookEmptyState = memo(OrderBookEmptyStateInner);
