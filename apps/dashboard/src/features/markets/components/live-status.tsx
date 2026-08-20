'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { formatRelative } from '../lib/format';

const UPDATING_WINDOW_MS = 15_000;

type FeedState = 'updating' | 'connected' | 'disconnected' | 'unknown';

function dotColor(state: FeedState): string {
  switch (state) {
    case 'updating':
      return 'info.main';
    case 'connected':
      return 'success.main';
    case 'disconnected':
      return 'error.main';
    default:
      return 'text.disabled';
  }
}

function feedLabel(state: FeedState): string {
  switch (state) {
    case 'updating':
      return 'Updating';
    case 'connected':
      return 'Connected';
    default:
      return 'Disconnected';
  }
}

interface LiveStatusProps {
  now: number;
  wsConnected: boolean;
  lastWsMessageAt: string | null;
  latestCandleTime: string | null;
  lastIngestionAt: string | null;
}

function StatusDot({ state }: { state: FeedState }) {
  const color = dotColor(state);
  return (
    <Box
      component="span"
      aria-hidden
      sx={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        bgcolor: color,
        flexShrink: 0,
        ...(state === 'updating'
          ? {
              '@keyframes statusPulse': {
                from: { opacity: 1 },
                to: { opacity: 0.35 },
              },
              animation: 'statusPulse 1.2s ease-in-out infinite',
            }
          : {}),
      }}
    />
  );
}

export function LiveStatus({
  now,
  wsConnected,
  lastWsMessageAt,
  latestCandleTime,
  lastIngestionAt,
}: LiveStatusProps) {
  const wsAge =
    lastWsMessageAt !== null ? Math.max(0, now - new Date(lastWsMessageAt).getTime()) : null;
  const updating = wsConnected && wsAge !== null && wsAge < UPDATING_WINDOW_MS;
  let feedState: FeedState = 'disconnected';
  if (updating) {
    feedState = 'updating';
  } else if (wsConnected) {
    feedState = 'connected';
  }

  return (
    <Stack spacing={1} role="status" aria-label="Live status">
      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
        <Chip
          label={wsConnected ? 'Live WebSocket' : 'REST snapshot'}
          color={wsConnected ? 'success' : 'default'}
          size="small"
          icon={
            <Box
              component="span"
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                bgcolor: wsConnected ? 'success.main' : 'text.disabled',
                ml: '8px !important',
              }}
              aria-hidden
            />
          }
        />
        <Chip label="Historical database" size="small" variant="outlined" />
      </Stack>
      <Stack spacing={0.75} aria-live="polite">
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Stack direction="row" spacing={0.75} alignItems="center" component="span">
            <StatusDot state={feedState} />
            <Typography variant="body2" color="text.secondary" component="dt">
              WebSocket feed
            </Typography>
          </Stack>
          <Typography variant="body2" component="dd" sx={{ m: 0, textAlign: 'right' }}>
            {feedLabel(feedState)}
            {' · '}Prices updated {formatRelative(lastWsMessageAt, now)}
          </Typography>
        </Stack>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Stack direction="row" spacing={0.75} alignItems="center" component="span">
            <StatusDot state={latestCandleTime !== null ? 'connected' : 'unknown'} />
            <Typography variant="body2" color="text.secondary" component="dt">
              Historical database
            </Typography>
          </Stack>
          <Typography variant="body2" component="dd" sx={{ m: 0, textAlign: 'right' }}>
            candles updated {formatRelative(latestCandleTime, now)}
          </Typography>
        </Stack>
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
          <Stack direction="row" spacing={0.75} alignItems="center" component="span">
            <StatusDot state={lastIngestionAt !== null ? 'connected' : 'unknown'} />
            <Typography variant="body2" color="text.secondary" component="dt">
              Synchronization
            </Typography>
          </Stack>
          <Typography variant="body2" component="dd" sx={{ m: 0, textAlign: 'right' }}>
            last sync {formatRelative(lastIngestionAt, now)}
          </Typography>
        </Stack>
      </Stack>
    </Stack>
  );
}
