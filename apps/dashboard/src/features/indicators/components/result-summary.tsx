'use client';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import RemoveIcon from '@mui/icons-material/Remove';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { FieldInfo } from './field-info';
import type { IndicatorKnowledge } from '../lib/indicator-knowledge';
import { summarizeSeries, type SeriesSummary } from '../lib/result-analysis';
import type { IndicatorSeries } from '@/types/api/indicators';

export interface ResultSummaryProps {
  series: readonly IndicatorSeries[];
  knowledge: IndicatorKnowledge;
}

/** Six significant digits: enough to read an indicator, without implying false precision. */
const valueFormatter = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 });
const percentFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
  signDisplay: 'always',
});
const changeFormatter = new Intl.NumberFormat(undefined, {
  maximumSignificantDigits: 4,
  signDisplay: 'always',
});

function formatValue(value: number | null): string {
  return value === null ? '—' : valueFormatter.format(value);
}

const TREND_ICON = {
  up: <ArrowUpwardIcon fontSize="inherit" />,
  down: <ArrowDownwardIcon fontSize="inherit" />,
  flat: <RemoveIcon fontSize="inherit" />,
} as const;

const TREND_COLOR = {
  up: 'success.main',
  down: 'error.main',
  flat: 'text.secondary',
} as const;

const SIGNAL_COLOR = {
  bullish: 'success',
  bearish: 'error',
  neutral: 'default',
} as const;

const SIGNAL_LABEL = {
  bullish: 'Bullish',
  bearish: 'Bearish',
  neutral: 'Neutral',
} as const;

function SeriesSummaryCard({ summary }: { summary: SeriesSummary }) {
  const trendColor = summary.trend ? TREND_COLOR[summary.trend] : 'text.secondary';

  return (
    <Box sx={{ minWidth: 220 }}>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Typography variant="caption" color="text.secondary">
          {summary.label}
        </Typography>
        <FieldInfo field="latestValue" label={`Latest ${summary.label}`} />
      </Stack>

      <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap">
        <Typography
          variant="h5"
          component="p"
          sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
        >
          {formatValue(summary.latest)}
        </Typography>
        {summary.signal ? (
          <Chip
            size="small"
            color={SIGNAL_COLOR[summary.signal]}
            label={SIGNAL_LABEL[summary.signal]}
          />
        ) : null}
      </Stack>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center" sx={{ mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          Previous: {formatValue(summary.previous)}
        </Typography>
        {summary.absoluteChange !== null ? (
          <Stack direction="row" spacing={0.25} alignItems="center" sx={{ color: trendColor }}>
            {summary.trend ? TREND_ICON[summary.trend] : null}
            <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {changeFormatter.format(summary.absoluteChange)}
              {summary.percentChange !== null
                ? ` (${percentFormatter.format(summary.percentChange)}%)`
                : ''}
            </Typography>
          </Stack>
        ) : null}
      </Stack>
    </Box>
  );
}

/**
 * Expands the previous single "Latest value" tile per series into the
 * full picture a researcher checks first: latest vs previous, the change
 * in both absolute and percentage terms, the trend direction, and — where
 * the indicator has an established convention (RSI's 30/70 thresholds) or
 * a generic trend-based fallback otherwise — a Bullish/Bearish/Neutral
 * signal badge. All computed by the pure, independently-tested
 * `summarizeSeries` (see `lib/result-analysis.ts`).
 */
function ResultSummaryInner({ series, knowledge }: ResultSummaryProps) {
  return (
    <Stack
      direction="row"
      spacing={{ xs: 2, sm: 3 }}
      flexWrap="wrap"
      useFlexGap
      role="status"
      aria-label="Indicator summary"
    >
      {series.map((entry) => (
        <SeriesSummaryCard key={entry.name} summary={summarizeSeries(entry, knowledge)} />
      ))}
    </Stack>
  );
}

export const ResultSummary = memo(ResultSummaryInner);
