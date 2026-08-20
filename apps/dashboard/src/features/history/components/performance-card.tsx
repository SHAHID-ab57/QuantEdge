'use client';

import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { formatNumber } from '../lib/format';
import type { HistoryQuery } from '../hooks/use-history-data';

interface PerformanceCardProps {
  query: HistoryQuery;
  page: number;
  latencyMs: number | null;
  returned: number;
  total: number;
}

function appliedFiltersLabel(query: HistoryQuery): string {
  const range = query.start && query.end ? `${query.start} → ${query.end}` : 'all history';
  return `${query.symbol} · ${query.timeframe} · ${range}`;
}

export function PerformanceCard({ query, page, latencyMs, returned, total }: PerformanceCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Query performance">
      <Typography variant="h6" component="h2" gutterBottom>
        Performance
      </Typography>
      <Stack component="dl" spacing={1} sx={{ m: 0 }}>
        <Stack direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="body2" color="text.secondary" component="dt">
            Rows returned
          </Typography>
          <Typography variant="body2" component="dd" sx={{ m: 0 }}>
            {formatNumber(returned)} of {formatNumber(total)}
          </Typography>
        </Stack>
        <Stack direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="body2" color="text.secondary" component="dt">
            API latency
          </Typography>
          <Typography variant="body2" component="dd" sx={{ m: 0 }}>
            {latencyMs !== null ? `${latencyMs.toFixed(1)} ms` : '—'}
          </Typography>
        </Stack>
        <Stack direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="body2" color="text.secondary" component="dt">
            Page
          </Typography>
          <Typography variant="body2" component="dd" sx={{ m: 0 }}>
            {page}
          </Typography>
        </Stack>
      </Stack>
      <Stack spacing={0.5} sx={{ mt: 1.5 }}>
        <Typography variant="overline" color="text.secondary" component="h3">
          Applied filters
        </Typography>
        <Chip
          label={appliedFiltersLabel(query)}
          size="small"
          variant="outlined"
          sx={{ alignSelf: 'flex-start', maxWidth: '100%' }}
        />
      </Stack>
    </Paper>
  );
}
