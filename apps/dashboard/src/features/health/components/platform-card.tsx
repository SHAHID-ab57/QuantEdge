'use client';

import SpeedIcon from '@mui/icons-material/Speed';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { SystemStatus } from '@/types/api/system';
import { useNow } from '../hooks/use-now';
import { formatDateTime, formatDuration } from '../lib/format';

export function PlatformCard({ status }: Readonly<{ status: SystemStatus }>) {
  const now = useNow();
  const startedAt = new Date(status.started_at).getTime();
  const uptimeSeconds = Math.max(0, (now - startedAt) / 1_000);

  return (
    <Paper component="section" aria-labelledby="platform-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="platform-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <SpeedIcon fontSize="small" color="action" />
        Platform
      </Typography>
      <Typography variant="h4" sx={{ mt: 1, fontVariantNumeric: 'tabular-nums' }}>
        {formatDuration(uptimeSeconds)}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        Uptime since {formatDateTime(status.started_at)}
      </Typography>
      <Stack direction="row" spacing={1} sx={{ mt: 2 }} useFlexGap flexWrap="wrap">
        <Chip size="small" label={`v${status.version}`} aria-label={`Version ${status.version}`} />
        <Chip
          size="small"
          label={status.environment}
          aria-label={`Environment ${status.environment}`}
        />
        {status.market_data_live ? (
          <Chip size="small" color="success" label="Live market data" />
        ) : (
          <Chip size="small" label="Live market data off" />
        )}
        {status.delta_ws_connected && (
          <Chip size="small" color="success" label="WebSocket connected" />
        )}
      </Stack>
      <Box sx={{ mt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Symbols tracked: {status.symbols_tracked}
        </Typography>
      </Box>
    </Paper>
  );
}
