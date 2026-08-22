'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { formatRelative } from '@/features/markets/lib/format';
import type { SystemHealth, SystemStatus } from '@/types/api/system';
import type { ConnectionState } from '../hooks/use-market-stream';

/** How stale the backend's last candle ingestion may be before it reads as degraded. */
const SYNC_STALE_MS = 15 * 60_000;

export type StatusTone = 'ok' | 'warn' | 'bad' | 'idle';

export interface ConnectionStatusProps {
  connectionState: ConnectionState;
  lastMessageAt: number | null;
  reconnectAttempt: number;
  latencyMs: number | null;
  health: SystemHealth | undefined;
  healthError: boolean;
  status: SystemStatus | undefined;
  now: number;
}

const TONE_COLOR: Record<StatusTone, string> = {
  ok: 'success.main',
  warn: 'warning.main',
  bad: 'error.main',
  idle: 'text.disabled',
};

const STREAM_LABEL: Record<ConnectionState, string> = {
  connecting: 'Connecting…',
  open: 'Connected',
  reconnecting: 'Reconnecting…',
  closed: 'Disconnected',
};

const STREAM_TONE: Record<ConnectionState, StatusTone> = {
  connecting: 'warn',
  open: 'ok',
  reconnecting: 'warn',
  closed: 'bad',
};

const COMPONENT_TONE: Record<string, StatusTone> = {
  ok: 'ok',
  degraded: 'warn',
  unavailable: 'bad',
};

interface StatusItemProps {
  label: string;
  value: string;
  tone: StatusTone;
  hint?: string;
}

function StatusItem({ label, value, tone, hint }: StatusItemProps) {
  const content = (
    <Stack spacing={0.25} sx={{ minWidth: 140 }}>
      <Typography variant="caption" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Stack direction="row" spacing={0.75} alignItems="center" component="dd" sx={{ m: 0 }}>
        <Box
          aria-hidden
          sx={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            bgcolor: TONE_COLOR[tone],
            flexShrink: 0,
          }}
        />
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {value}
        </Typography>
      </Stack>
    </Stack>
  );
  return hint ? (
    <Tooltip title={hint}>
      <Box>{content}</Box>
    </Tooltip>
  ) : (
    content
  );
}

function backendItem(health: SystemHealth | undefined, healthError: boolean): StatusItemProps {
  if (healthError) {
    return { label: 'Backend API', value: 'Unreachable', tone: 'bad' };
  }
  if (!health) {
    return { label: 'Backend API', value: 'Checking…', tone: 'idle' };
  }
  const latency = health.api.latency_ms ?? null;
  return {
    label: 'Backend API',
    value: latency === null ? health.api.status : `${health.api.status} · ${latency.toFixed(0)}ms`,
    tone: COMPONENT_TONE[health.api.status] ?? 'idle',
    hint: health.api.detail ?? undefined,
  };
}

function syncItem(status: SystemStatus | undefined, now: number): StatusItemProps {
  const lastIngestion = status?.last_ingestion_at ?? null;
  if (!status) {
    return { label: 'Historical Sync', value: 'Checking…', tone: 'idle' };
  }
  if (!lastIngestion) {
    return {
      label: 'Historical Sync',
      value: 'Never run',
      tone: 'warn',
      hint: 'The backend has not ingested any candles since it started.',
    };
  }
  const stale = now - new Date(lastIngestion).getTime() > SYNC_STALE_MS;
  return {
    label: 'Historical Sync',
    value: formatRelative(lastIngestion, now),
    tone: stale ? 'warn' : 'ok',
    hint: stale
      ? 'No candles ingested recently — stored history may lag the live feed.'
      : 'Time since the backend last ingested candles.',
  };
}

function marketStateItem(
  health: SystemHealth | undefined,
  status: SystemStatus | undefined,
): StatusItemProps {
  if (!health) {
    return { label: 'Market State', value: 'Checking…', tone: 'idle' };
  }
  const tracked = status?.symbols_tracked ?? null;
  return {
    label: 'Market State',
    value:
      tracked === null
        ? health.state_manager.status
        : `${health.state_manager.status} · ${tracked} symbol${tracked === 1 ? '' : 's'}`,
    tone: COMPONENT_TONE[health.state_manager.status] ?? 'idle',
    hint: 'Symbols the backend is holding live state for.',
  };
}

/**
 * Operational status for everything the live view depends on: the REST API
 * and the backend's own components (polled from `/system/*`, shared with the
 * Health page's queries) alongside this page's own WebSocket connection,
 * whose state only the client knows.
 *
 * `Latency` is the round-trip time of the stream's own heartbeat, so it
 * measures the path the live data actually travels rather than a REST call.
 */
function ConnectionStatusInner({
  connectionState,
  lastMessageAt,
  reconnectAttempt,
  latencyMs,
  health,
  healthError,
  status,
  now,
}: ConnectionStatusProps) {
  const items: StatusItemProps[] = [
    backendItem(health, healthError),
    {
      label: 'WebSocket',
      value: STREAM_LABEL[connectionState],
      tone: STREAM_TONE[connectionState],
      hint: 'This browser’s connection to the backend market-stream gateway.',
    },
    syncItem(status, now),
    marketStateItem(health, status),
    {
      label: 'Last Message',
      value:
        lastMessageAt === null
          ? 'None yet'
          : formatRelative(new Date(lastMessageAt).toISOString(), now),
      tone: lastMessageAt === null ? 'idle' : 'ok',
    },
    {
      label: 'Reconnect Attempts',
      value: String(reconnectAttempt),
      tone: reconnectAttempt === 0 ? 'ok' : 'warn',
    },
    {
      label: 'Latency',
      value: latencyMs === null ? 'Unavailable' : `${latencyMs}ms`,
      tone: latencyMs === null ? 'idle' : 'ok',
      hint: 'Heartbeat round-trip over the live stream.',
    },
  ];

  return (
    <Paper
      variant="outlined"
      sx={{ p: 2 }}
      role="status"
      aria-label="Live stream connection status"
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2" component="h2">
          Connection
        </Typography>
        <Chip
          size="small"
          color={connectionState === 'open' ? 'success' : 'warning'}
          label={STREAM_LABEL[connectionState]}
        />
      </Stack>
      <Box component="dl" sx={{ m: 0, display: 'flex', flexWrap: 'wrap', gap: 2, rowGap: 1.5 }}>
        {items.map((item) => (
          <StatusItem key={item.label} {...item} />
        ))}
      </Box>
    </Paper>
  );
}

export const ConnectionStatus = memo(ConnectionStatusInner);
