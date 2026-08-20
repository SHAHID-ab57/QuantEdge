'use client';

import Alert from '@mui/material/Alert';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { CandleQuality } from '@/types/api/market';
import { formatNumber } from '../lib/format';

interface QualityCardProps {
  quality: CandleQuality | undefined;
  isLoading: boolean;
  isEmpty: boolean;
}

function QualityRow({ label, value }: { label: string; value: string }) {
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

function formatScore(value: number | undefined): string {
  if (value === undefined) {
    return '—';
  }
  return `${value.toFixed(1)} of 100`;
}

export function QualityCard({ quality, isLoading, isEmpty }: QualityCardProps) {
  const overall = quality?.overall_quality_score;
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Data quality">
      <Typography variant="h6" component="h2" gutterBottom>
        Data Quality
      </Typography>
      {isLoading ? (
        <Stack spacing={1.5} role="status" aria-label="Loading data quality">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} variant="text" />
          ))}
        </Stack>
      ) : null}
      {isEmpty ? (
        <Alert severity="info" role="status" aria-label="No quality metrics available">
          No quality metrics for an empty range.
        </Alert>
      ) : null}
      {quality ? (
        <Stack component="dl" spacing={1} sx={{ m: 0 }}>
          <QualityRow label="Overall quality" value={formatScore(overall)} />
          {overall !== undefined ? (
            <LinearProgress
              variant="determinate"
              value={Math.max(0, Math.min(100, overall))}
              aria-label="Overall quality score"
              sx={{ mb: 1 }}
            />
          ) : null}
          <QualityRow label="Completeness" value={formatScore(quality.completeness_score)} />
          <QualityRow label="Freshness" value={formatScore(quality.freshness_score)} />
          <QualityRow
            label="Missing intervals"
            value={formatNumber(quality.missing_interval_count)}
          />
          <QualityRow label="Duplicate buckets" value={formatNumber(quality.duplicate_candles)} />
          <QualityRow
            label="Out-of-order candles"
            value={formatNumber(quality.out_of_order_candles)}
          />
          <QualityRow
            label="Invalid OHLC candles"
            value={formatNumber(quality.invalid_ohlc_candles)}
          />
          <QualityRow label="Gaps detected" value={quality.gaps_detected ? 'Yes' : 'No'} />
        </Stack>
      ) : null}
    </Paper>
  );
}
