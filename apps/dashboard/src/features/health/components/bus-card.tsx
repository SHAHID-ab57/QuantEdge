'use client';

import AltRouteIcon from '@mui/icons-material/AltRoute';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import type { SystemMetrics } from '@/types/api/system';
import { formatLatency, formatNumber } from '../lib/format';
import { Metric } from './primitives';

export function BusCard({ metrics }: Readonly<{ metrics: SystemMetrics }>) {
  return (
    <Paper component="section" aria-labelledby="bus-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="bus-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <AltRouteIcon fontSize="small" color="action" />
        Event Bus
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
        <Metric label="Subscribers" value={formatNumber(metrics.event_bus_subscribers)} />
        <Metric label="Events published" value={formatNumber(metrics.event_bus_published)} />
        <Metric
          label="Pending queue"
          value={formatNumber(metrics.event_bus_pending)}
          emphasis={metrics.event_bus_pending > 0}
        />
        <Metric
          label="Failed handlers"
          value={formatNumber(metrics.event_bus_failed_handlers)}
          emphasis={metrics.event_bus_failed_handlers > 0}
        />
        <Metric
          label="Handler latency"
          value={formatLatency(metrics.event_bus_average_handler_latency_ms)}
        />
      </Box>
    </Paper>
  );
}
