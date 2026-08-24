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
  /**
   * The current market price, in the same units as the indicator's own
   * `source` — sourced from the market's latest stored candle, entirely
   * independent of the calculation response (which carries no raw price
   * data). Omitted while that lookup hasn't resolved yet; the Current
   * Price / Distance rows simply don't render without it.
   */
  currentPrice?: number;
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

const STATE_COLOR = {
  notable: 'warning',
  neutral: 'default',
} as const;

const STATUS_LABEL = {
  computed: 'Computed',
  'warming-up': 'Warming up',
} as const;

function ChangeRow({ summary }: { summary: SeriesSummary }) {
  const trendColor = summary.trend ? TREND_COLOR[summary.trend] : 'text.secondary';
  if (summary.absoluteChange === null) {
    return null;
  }
  return (
    <Stack direction="row" spacing={0.25} alignItems="center" sx={{ color: trendColor }}>
      {summary.trend ? TREND_ICON[summary.trend] : null}
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {changeFormatter.format(summary.absoluteChange)}
        {summary.percentChange !== null
          ? ` (${percentFormatter.format(summary.percentChange)}%)`
          : ''}
      </Typography>
    </Stack>
  );
}

function DistanceFromPrice({
  latest,
  currentPrice,
}: {
  latest: number | null;
  currentPrice: number;
}) {
  if (latest === null) {
    return null;
  }
  const distance = latest - currentPrice;
  const percent = currentPrice !== 0 ? (distance / Math.abs(currentPrice)) * 100 : null;
  return (
    <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center">
      <Typography variant="caption" color="text.secondary">
        Current Price: {valueFormatter.format(currentPrice)}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ fontVariantNumeric: 'tabular-nums' }}
      >
        Distance: {changeFormatter.format(distance)}
        {percent !== null ? ` (${percentFormatter.format(percent)}%)` : ''}
      </Typography>
    </Stack>
  );
}

function SeriesSummaryCard({
  summary,
  currentPrice,
}: {
  summary: SeriesSummary;
  currentPrice?: number;
}) {
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
        {summary.state ? (
          <Chip size="small" color={STATE_COLOR[summary.state.tone]} label={summary.state.label} />
        ) : null}
      </Stack>

      <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center" sx={{ mt: 0.5 }}>
        <Typography variant="caption" color="text.secondary">
          Previous: {formatValue(summary.previous)}
        </Typography>
        <ChangeRow summary={summary} />
      </Stack>

      {currentPrice !== undefined ? (
        <Box sx={{ mt: 0.5 }}>
          <DistanceFromPrice latest={summary.latest} currentPrice={currentPrice} />
        </Box>
      ) : null}

      <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 0.5 }}>
        Status: {STATUS_LABEL[summary.status]}
      </Typography>
    </Box>
  );
}

/**
 * Expands the previous single "Latest value" tile per series into the
 * full analytical picture a researcher checks first: latest vs previous,
 * the change in both absolute and percentage terms, the trend direction,
 * distance from the current market price, and — only where the indicator
 * has an established convention for one (RSI's 30/70 thresholds) — a
 * descriptive state label. This page displays analytical information
 * only; it never classifies a plain moving average's direction as
 * "bullish" or "bearish", since that would be manufacturing a trading
 * signal out of a number that doesn't carry one. All computed by the
 * pure, independently-tested `summarizeSeries` (see `lib/result-analysis.ts`).
 */
function ResultSummaryInner({ series, knowledge, currentPrice }: ResultSummaryProps) {
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
        <SeriesSummaryCard
          key={entry.name}
          summary={summarizeSeries(entry, knowledge)}
          currentPrice={currentPrice}
        />
      ))}
    </Stack>
  );
}

export const ResultSummary = memo(ResultSummaryInner);
