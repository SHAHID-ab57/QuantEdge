'use client';

import Alert from '@mui/material/Alert';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { CandleStatistics } from '@/types/api/market';
import { formatDateTime, formatDecimal, formatNumber } from '../lib/format';

interface StatsCardProps {
  statistics: CandleStatistics | undefined;
  isLoading: boolean;
  isEmpty: boolean;
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={2}>
      <Typography variant="body2" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography variant="body2" component="dd" sx={{ textAlign: 'right', fontWeight: 600 }}>
        {value}
      </Typography>
    </Stack>
  );
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  return `${value.toFixed(1)}%`;
}

export function StatsCard({ statistics, isLoading, isEmpty }: StatsCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Candle statistics">
      <Typography variant="h6" component="h2" gutterBottom>
        Statistics
      </Typography>
      {isLoading ? (
        <Stack spacing={1.5} role="status" aria-label="Loading statistics">
          {Array.from({ length: 10 }, (_, index) => (
            <Skeleton key={index} variant="text" />
          ))}
        </Stack>
      ) : null}
      {isEmpty ? (
        <Alert severity="info" role="status" aria-label="No statistics available">
          No candle data in this range for the selected market and timeframe.
        </Alert>
      ) : null}
      {statistics ? (
        <Stack component="dl" spacing={1} sx={{ m: 0 }}>
          <StatRow label="Highest price" value={formatDecimal(statistics.highest_price)} />
          <StatRow label="Lowest price" value={formatDecimal(statistics.lowest_price)} />
          <StatRow label="Highest volume" value={formatDecimal(statistics.highest_volume)} />
          <StatRow label="Lowest volume" value={formatDecimal(statistics.lowest_volume)} />
          <StatRow label="Average open" value={formatDecimal(statistics.average_open)} />
          <StatRow label="Average close" value={formatDecimal(statistics.average_close)} />
          <StatRow label="Average high" value={formatDecimal(statistics.average_high)} />
          <StatRow label="Average low" value={formatDecimal(statistics.average_low)} />
          <StatRow label="Average volume" value={formatDecimal(statistics.average_volume)} />
          <Divider sx={{ my: 0.5 }} />
          <StatRow label="Total candles" value={formatNumber(statistics.total_candles)} />
          <StatRow label="Expected candles" value={formatNumber(statistics.expected_candles)} />
          <StatRow label="Missing candles" value={formatNumber(statistics.missing_candles)} />
          <StatRow label="Completeness" value={formatPercent(statistics.completeness)} />
          <Divider sx={{ my: 0.5 }} />
          <StatRow label="First candle" value={formatDateTime(statistics.first_candle_at)} />
          <StatRow label="Last candle" value={formatDateTime(statistics.last_candle_at)} />
        </Stack>
      ) : null}
    </Paper>
  );
}
