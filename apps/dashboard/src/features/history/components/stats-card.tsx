'use client';

import Alert from '@mui/material/Alert';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { CandleStats } from '@/types/api/market';
import { formatDateTime, formatDecimal, formatNumber } from '../lib/format';

interface StatsCardProps {
  stats: CandleStats | undefined;
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

export function StatsCard({ stats, isLoading, isEmpty }: StatsCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Candle statistics">
      <Typography variant="h6" component="h2" gutterBottom>
        Statistics
      </Typography>
      {isLoading ? (
        <Stack spacing={1.5} role="status" aria-label="Loading statistics">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} variant="text" />
          ))}
        </Stack>
      ) : null}
      {isEmpty ? (
        <Alert severity="info" role="status" aria-label="No statistics available">
          No candle data in this range for the selected market and timeframe.
        </Alert>
      ) : null}
      {stats ? (
        <Stack component="dl" spacing={1} sx={{ m: 0 }}>
          <StatRow label="Highest price" value={formatDecimal(stats.highest_price)} />
          <StatRow label="Lowest price" value={formatDecimal(stats.lowest_price)} />
          <StatRow label="Average volume" value={formatDecimal(stats.average_volume)} />
          <StatRow label="Total candles" value={formatNumber(stats.total_candles)} />
          <Divider sx={{ my: 0.5 }} />
          <StatRow
            label="First candle"
            value={stats.first_candle ? formatDateTime(stats.first_candle.open_time) : '—'}
          />
          <StatRow
            label="Last candle"
            value={stats.last_candle ? formatDateTime(stats.last_candle.open_time) : '—'}
          />
        </Stack>
      ) : null}
    </Paper>
  );
}
