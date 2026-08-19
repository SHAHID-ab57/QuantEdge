'use client';

import HistoryIcon from '@mui/icons-material/History';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import type { SystemStatus } from '@/types/api/system';
import { useNow } from '../hooks/use-now';
import { formatDateTime, formatRelative } from '../lib/format';
import { MetricRow } from './primitives';

export function TimelineCard({ status }: Readonly<{ status: SystemStatus }>) {
  const now = useNow();
  const rows: { label: string; iso: string | null | undefined; tone?: 'ok' | 'warn' | 'err' }[] = [
    { label: 'Last heartbeat', iso: status.last_heartbeat_at, tone: 'ok' },
    { label: 'Last WebSocket message', iso: status.last_ws_message_at, tone: 'ok' },
    { label: 'Last WebSocket reconnect', iso: status.last_ws_reconnect_at },
    { label: 'Last REST request', iso: status.last_rest_request_at },
    { label: 'Last ingestion', iso: status.last_ingestion_at },
  ];

  return (
    <Paper component="section" aria-labelledby="timeline-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="timeline-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <HistoryIcon fontSize="small" color="action" />
        Health Timeline
      </Typography>
      <Box component="dl" sx={{ m: 0, mt: 1 }}>
        {rows.map((row) => (
          <MetricRow
            key={row.label}
            label={row.label}
            tone={row.tone}
            value={
              row.iso ? (
                <Box component="span" title={formatDateTime(row.iso)}>
                  {formatRelative(row.iso, now)}
                </Box>
              ) : (
                '—'
              )
            }
          />
        ))}
      </Box>
    </Paper>
  );
}
