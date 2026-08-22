'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { formatRelative } from '@/features/markets/lib/format';
import type { MarketReadiness } from '../lib/market-selection';
import type { ConnectionState } from '../hooks/use-market-stream';

export interface MarketDataNoticeProps {
  symbol: string;
  readiness: MarketReadiness | null;
  connectionState: ConnectionState;
  lastMessageAt: number | null;
  hasPrice: boolean;
  now: number;
  onRetry: () => void;
}

/**
 * Explains *why* the live view is short of data instead of showing a bare
 * "waiting…" message: which of the three preconditions (stored candles,
 * live feed, an actual tick) is missing, whether the socket is even
 * connected, and when the last message arrived — with a retry for the cases
 * a refetch can fix.
 *
 * Renders nothing once the market is fully ready and a price has arrived,
 * so it never adds noise to a healthy dashboard.
 */
function MarketDataNoticeInner({
  symbol,
  readiness,
  connectionState,
  lastMessageAt,
  hasPrice,
  now,
  onRetry,
}: MarketDataNoticeProps) {
  const missingHistory = readiness !== null && !readiness.hasHistoricalCandles;
  const missingLive = readiness !== null && !readiness.hasLiveSupport;
  const connected = connectionState === 'open';

  if (!missingHistory && !missingLive && hasPrice) {
    return null;
  }

  const severity = missingHistory || missingLive ? 'warning' : 'info';
  const title = (() => {
    if (missingHistory && missingLive) {
      return `No data is available for ${symbol}`;
    }
    if (missingHistory) {
      return `No stored history for ${symbol}`;
    }
    if (missingLive) {
      return `${symbol} is not on the live feed`;
    }
    return `Waiting for the first ${symbol} update`;
  })();

  const lines: string[] = [...(readiness?.blockers ?? [])];
  if (!connected) {
    lines.push(
      connectionState === 'reconnecting'
        ? 'The live stream dropped and is reconnecting automatically.'
        : 'The live stream is not connected yet.',
    );
  } else if (!hasPrice) {
    lines.push('The live stream is connected; no price has been received for this market yet.');
  }
  lines.push(
    lastMessageAt === null
      ? 'No message has been received on the stream yet.'
      : `Last stream message ${formatRelative(new Date(lastMessageAt).toISOString(), now)}.`,
  );

  return (
    <Alert
      severity={severity}
      role="status"
      aria-label={`Data availability for ${symbol}`}
      action={
        <Button size="small" onClick={onRetry}>
          Retry
        </Button>
      }
    >
      <AlertTitle>{title}</AlertTitle>
      <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2 }}>
        {lines.map((line) => (
          <Typography key={line} variant="body2" component="li">
            {line}
          </Typography>
        ))}
      </Stack>
    </Alert>
  );
}

export const MarketDataNotice = memo(MarketDataNoticeInner);
