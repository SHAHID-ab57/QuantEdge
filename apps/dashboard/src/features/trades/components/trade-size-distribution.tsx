'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { formatNumber } from '@/features/markets/lib/format';
import type { SizeDistribution } from '../lib/size-distribution';
import { MetricInfo } from './metric-info';

export interface TradeSizeDistributionProps {
  distribution: SizeDistribution;
}

/**
 * A horizontal histogram of the last minute's trade sizes, bucketed
 * relative to that window's own average (see `lib/size-distribution.ts`
 * for why relative bucketing rather than absolute). Answers the question a
 * bare "average trade size" can't: is this many similar prints, or a
 * handful of outliers dragging the average around?
 *
 * Rendered as plain `Box` bars rather than a charting library — five bars
 * do not justify a chart instance, and this keeps it a pure function of the
 * distribution with nothing to tear down.
 */
function TradeSizeDistributionInner({ distribution }: TradeSizeDistributionProps) {
  const hasData = distribution.total > 0;
  const peakShare = Math.max(...distribution.buckets.map((bucket) => bucket.share), 0);

  return (
    <Stack spacing={1} sx={{ minWidth: 220, flex: '1 1 240px' }}>
      <Stack direction="row" spacing={0.25} alignItems="center">
        <Typography variant="caption" color="text.secondary">
          Trade Size Distribution
        </Typography>
        <MetricInfo metric="sizeDistribution" label="Trade Size Distribution" />
        <Typography variant="caption" color="text.disabled" sx={{ ml: 0.5 }}>
          {hasData ? `${formatNumber(distribution.total)} trades` : 'no trades yet'}
        </Typography>
      </Stack>
      <Stack
        spacing={0.5}
        role="group"
        aria-label="Trade size distribution over the last minute, by multiple of average size"
      >
        {distribution.buckets.map((bucket) => {
          // Bars are scaled against the tallest bucket, not against 100%, so
          // the shape stays readable when every bucket holds a small share.
          const width = peakShare > 0 ? (bucket.share / peakShare) * 100 : 0;
          const percent = Math.round(bucket.share * 100);
          return (
            <Stack key={bucket.label} direction="row" spacing={1} alignItems="center">
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  width: 48,
                  flexShrink: 0,
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {bucket.label}
              </Typography>
              <Box
                sx={{
                  flex: 1,
                  height: 10,
                  borderRadius: 0.5,
                  bgcolor: 'action.disabledBackground',
                  overflow: 'hidden',
                }}
              >
                <Box
                  role="meter"
                  aria-label={`Trades between ${bucket.label} of average size`}
                  aria-valuenow={percent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuetext={`${percent}% of trades, ${bucket.count} of ${distribution.total}`}
                  sx={{
                    width: `${width}%`,
                    height: '100%',
                    // The top bucket is the "unusually large" tail — worth
                    // distinguishing, since it is what pulls the average.
                    bgcolor: bucket.maxMultiple === null ? 'warning.main' : 'primary.main',
                    transition: 'width 250ms ease-out',
                  }}
                />
              </Box>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  width: 34,
                  flexShrink: 0,
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {hasData ? `${percent}%` : '—'}
              </Typography>
            </Stack>
          );
        })}
      </Stack>
    </Stack>
  );
}

export const TradeSizeDistribution = memo(TradeSizeDistributionInner);
