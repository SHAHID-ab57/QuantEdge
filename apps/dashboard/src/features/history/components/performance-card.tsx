'use client';

import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { QueryMetadata } from '@/types/api/market';
import type { HistoryQuery } from '../hooks/use-history-data';
import { formatDateTime, formatNumber } from '../lib/format';

interface PerformanceCardProps {
  query: HistoryQuery;
  page: number;
  meta: QueryMetadata | undefined;
  returned: number;
  total: number;
}

function appliedFiltersLabel(query: HistoryQuery): string {
  const range = query.start && query.end ? `${query.start} → ${query.end}` : 'all history';
  return `${query.symbol} · ${query.timeframe} · ${range}`;
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="body2" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography variant="body2" component="dd" sx={{ m: 0 }}>
        {value}
      </Typography>
    </Stack>
  );
}

export function PerformanceCard({ query, page, meta, returned, total }: PerformanceCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Query performance">
      <Typography variant="h6" component="h2" gutterBottom>
        Performance
      </Typography>
      <Stack component="dl" spacing={1} sx={{ m: 0 }}>
        <MetaRow
          label="Rows returned"
          value={`${formatNumber(returned)} of ${formatNumber(total)}`}
        />
        <MetaRow
          label="Server execution"
          value={meta ? `${meta.execution_time_ms.toFixed(1)} ms` : '—'}
        />
        <MetaRow
          label="Database time"
          value={meta ? `${meta.database_time_ms.toFixed(1)} ms` : '—'}
        />
        <MetaRow label="Rows scanned" value={meta ? formatNumber(meta.rows_scanned) : '—'} />
        <MetaRow label="Cache" value={meta ? meta.cache_status : '—'} />
        <MetaRow label="Generated at" value={meta ? formatDateTime(meta.generated_at) : '—'} />
        <MetaRow label="Page" value={String(page)} />
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
