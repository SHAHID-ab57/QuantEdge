'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo, type ReactNode } from 'react';

export interface BuySellPressureBarProps {
  label: string;
  buyVolume: number;
  sellVolume: number;
  /** Rendered beside the label — the analytics dashboard passes its `MetricInfo` button. */
  info?: ReactNode;
}

/**
 * A compact split bar: buy volume's share on the left (green), sell
 * volume's share on the right (red) — a proportional-width alternative to
 * reading "Buy/Sell Ratio" as a bare number. Used at both the session level
 * (`StatsCards`) and the rolling one-minute level (`MarketSentimentPanel`),
 * which is why it takes plain `buyVolume`/`sellVolume` rather than a
 * specific stats shape.
 */
function BuySellPressureBarInner({ label, buyVolume, sellVolume, info }: BuySellPressureBarProps) {
  const total = buyVolume + sellVolume;
  const buyPercent = total > 0 ? (buyVolume / total) * 100 : 50;
  const sellPercent = 100 - buyPercent;
  const hasData = total > 0;

  return (
    <Stack spacing={0.5} sx={{ minWidth: 160 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {label}
          </Typography>
          {info}
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {hasData ? `${buyPercent.toFixed(0)}% / ${sellPercent.toFixed(0)}%` : 'Unavailable'}
        </Typography>
      </Stack>
      <Box
        role="meter"
        aria-label={label}
        aria-valuenow={hasData ? Math.round(buyPercent) : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        sx={{
          display: 'flex',
          height: 8,
          borderRadius: 1,
          overflow: 'hidden',
          bgcolor: 'action.disabledBackground',
        }}
      >
        <Box
          sx={{
            width: `${hasData ? buyPercent : 50}%`,
            bgcolor: hasData ? 'success.main' : 'action.disabled',
            transition: 'width 200ms ease-out',
          }}
        />
        <Box
          sx={{
            width: `${hasData ? sellPercent : 50}%`,
            bgcolor: hasData ? 'error.main' : 'action.disabled',
            transition: 'width 200ms ease-out',
          }}
        />
      </Box>
    </Stack>
  );
}

export const BuySellPressureBar = memo(BuySellPressureBarInner);
