'use client';

import StreamIcon from '@mui/icons-material/Stream';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import type { SystemMetrics } from '@/types/api/system';
import { formatLatency, formatNumber } from '../lib/format';
import { Metric } from './primitives';

export function ProcessingCard({ metrics }: Readonly<{ metrics: SystemMetrics }>) {
  return (
    <Paper component="section" aria-labelledby="processing-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="processing-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <StreamIcon fontSize="small" color="action" />
        Message Processing
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
        <Metric label="Raw messages" value={formatNumber(metrics.messages_received)} />
        <Metric label="Normalized" value={formatNumber(metrics.messages_normalized)} />
        <Metric label="Events published" value={formatNumber(metrics.events_published)} />
        <Metric label="Validation failures" value={formatNumber(metrics.validation_failures)} />
        <Metric label="Unsupported" value={formatNumber(metrics.unsupported_messages)} />
        <Metric
          label="Processing latency"
          value={formatLatency(metrics.average_pipeline_latency_ms)}
        />
      </Box>
    </Paper>
  );
}
