'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { splitLabelText, type SplitLabel } from '@/lib/split-label';
import type { SplitRatioValues } from '../lib/split-ratios';

export interface SplitTimelineProps {
  values: SplitRatioValues;
  /** Total rows the split would be applied to, if already known from a previous build. */
  estimatedTotalRows?: number;
}

const SEGMENT_COLOR: Record<SplitLabel, string> = {
  train: 'primary.main',
  validation: 'info.main',
  test: 'warning.main',
};

/**
 * A horizontal, proportional bar showing the train/validation/test split
 * in the exact chronological order it is actually applied — train first,
 * then validation, then test, left to right — so "chronological, never
 * shuffled" is something a researcher can see, not just read in a
 * tooltip. Purely presentational: it renders `values` as given and never
 * itself decides what a valid split looks like (see `split-ratios.ts` for
 * that).
 */
export function SplitTimeline({ values, estimatedTotalRows }: SplitTimelineProps) {
  const segments: { label: SplitLabel; ratio: number }[] = [
    { label: 'train', ratio: values.train },
    { label: 'validation', ratio: values.validation },
    { label: 'test', ratio: values.test },
  ];

  return (
    <Stack spacing={0.5} aria-label="Split timeline">
      <Box
        sx={{
          display: 'flex',
          width: '100%',
          height: 28,
          borderRadius: 1,
          overflow: 'hidden',
          border: '1px solid',
          borderColor: 'divider',
        }}
      >
        {segments.map((segment) =>
          segment.ratio > 0 ? (
            <Box
              key={segment.label}
              sx={{
                width: `${segment.ratio * 100}%`,
                bgcolor: SEGMENT_COLOR[segment.label],
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: segment.ratio > 0 ? 2 : 0,
              }}
              title={`${splitLabelText(segment.label)}: ${(segment.ratio * 100).toFixed(0)}%`}
            />
          ) : null,
        )}
      </Box>
      <Stack direction="row" justifyContent="space-between">
        {segments.map((segment) => (
          <Stack key={segment.label} alignItems="center" spacing={0}>
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              {splitLabelText(segment.label)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {(segment.ratio * 100).toFixed(0)}%
              {estimatedTotalRows !== undefined
                ? ` · ~${Math.round(segment.ratio * estimatedTotalRows).toLocaleString()} rows`
                : ''}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
