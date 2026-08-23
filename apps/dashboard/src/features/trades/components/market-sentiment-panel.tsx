'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import type { RollingAnalytics } from '../lib/rolling-window';
import type { MarketSentiment } from '../lib/sentiment';
import { BuySellPressureBar } from './buy-sell-pressure-bar';
import { MetricInfo } from './metric-info';

export interface MarketSentimentPanelProps {
  sentiment: MarketSentiment;
  rolling: Pick<RollingAnalytics, 'buyVolume' | 'sellVolume'>;
}

const CHIP_COLOR: Record<MarketSentiment['label'], 'success' | 'error' | 'default'> = {
  'strongly-bullish': 'success',
  bullish: 'success',
  neutral: 'default',
  bearish: 'error',
  'strongly-bearish': 'error',
};

/**
 * A qualitative summary of the trailing one-minute buy/sell imbalance
 * (`RollingAnalytics.buySellImbalance`) — a fixed threshold rule over a
 * figure this dashboard already computes (`lib/sentiment.ts`), plus a
 * compact pressure bar for the same underlying volumes. Not a prediction or
 * a trading signal: it classifies what already happened in the last
 * minute, nothing about what happens next — which the metric's own tooltip
 * says explicitly, so the label can't be mistaken for a forecast.
 */
function MarketSentimentPanelInner({ sentiment, rolling }: MarketSentimentPanelProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: { xs: 2, sm: 3 },
        alignItems: 'center',
      }}
      role="status"
      aria-label="Market sentiment"
    >
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Market Sentiment
          </Typography>
          <MetricInfo metric="marketSentiment" label="Market Sentiment" />
        </Stack>
        <Chip
          label={sentiment.text}
          color={CHIP_COLOR[sentiment.label]}
          size="small"
          sx={{ fontWeight: 700, letterSpacing: 0.2 }}
        />
      </Stack>
      <BuySellPressureBar
        label="Buy/Sell Pressure — last minute"
        buyVolume={rolling.buyVolume}
        sellVolume={rolling.sellVolume}
        info={<MetricInfo metric="buySellPressure" label="Buy/Sell Pressure" />}
      />
    </Box>
  );
}

export const MarketSentimentPanel = memo(MarketSentimentPanelInner);
