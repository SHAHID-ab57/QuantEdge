'use client';

import StorageIcon from '@mui/icons-material/Storage';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import type { SystemMetrics } from '@/types/api/system';
import { formatNumber } from '../lib/format';
import { Metric } from './primitives';

export function DatabaseCard({ metrics }: Readonly<{ metrics: SystemMetrics }>) {
  return (
    <Paper component="section" aria-labelledby="database-stats-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="database-stats-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <StorageIcon fontSize="small" color="action" />
        Database
      </Typography>
      <Box
        component="dl"
        sx={{
          m: 0,
          mt: 1.5,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: 2,
        }}
      >
        <Metric label="Synchronized markets" value={formatNumber(metrics.synchronized_markets)} />
        <Metric label="Stored candles" value={formatNumber(metrics.stored_candles)} />
      </Box>
    </Paper>
  );
}
