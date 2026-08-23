'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatNumber } from '@/features/markets/lib/format';
import type { MetricHistory } from '../lib/metric-history';
import type { RollingAnalytics } from '../lib/rolling-window';
import { MetricInfo } from './metric-info';
import { Sparkline } from './sparkline';

export interface RollingAnalyticsPanelProps {
  rolling: RollingAnalytics;
  history: MetricHistory;
}

const UNAVAILABLE = 'Unavailable';

function imbalanceColor(value: number | null): string | undefined {
  if (value === null || value === 0) {
    return undefined;
  }
  return value > 0 ? 'success.main' : 'error.main';
}

function formatImbalance(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  const percent = (value * 100).toFixed(0);
  return value > 0 ? `+${percent}%` : `${percent}%`;
}

/**
 * Trades/minute, volume/minute, average trade size, and buy/sell imbalance —
 * all computed over the trailing one-minute window (`computeRollingAnalytics`,
 * `lib/rolling-window.ts`), recomputed on every new trade *and* on a
 * 1-second wall-clock tick so the window visibly empties out during a quiet
 * market instead of freezing on whatever it last showed. Each figure that
 * benefits from a trend carries a small sparkline from `history`
 * (`lib/metric-history.ts`), sampled roughly every 2 seconds — a separate,
 * much smaller ring buffer from the trade-level rolling window this panel's
 * own numbers come from.
 *
 * Renders bare tiles; the page wraps it in a `Section` that supplies the
 * heading and border.
 */
function RollingAnalyticsPanelInner({ rolling, history }: RollingAnalyticsPanelProps) {
  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 3 }, alignItems: 'center' }}
      role="status"
      aria-label="Rolling analytics (last minute)"
    >
      <Stack spacing={0.5}>
        <StatTile
          label="Trades / Minute"
          value={formatNumber(rolling.tradesPerMinute)}
          adornment={<MetricInfo metric="tradesPerMinute" label="Trades per Minute" />}
        />
        <Sparkline
          values={history.tradesPerMinute}
          ariaLabel="Trades per minute trend"
          color="#a78bfa"
        />
      </Stack>
      <Stack spacing={0.5}>
        <StatTile
          label="Volume / Minute"
          value={formatNumber(rolling.volumePerMinute)}
          adornment={<MetricInfo metric="volumePerMinute" label="Volume per Minute" />}
        />
        <Sparkline
          values={history.volumePerMinute}
          ariaLabel="Volume per minute trend"
          color="var(--mui-palette-info-main)"
        />
      </Stack>
      <Stack spacing={0.5}>
        <StatTile
          label="Average Trade Size"
          value={rolling.avgTradeSize === null ? UNAVAILABLE : formatNumber(rolling.avgTradeSize)}
          adornment={<MetricInfo metric="rollingAvgTradeSize" label="Rolling Average Trade Size" />}
        />
        <Sparkline
          values={history.avgTradeSize}
          ariaLabel="Average trade size trend"
          color="var(--mui-palette-warning-main)"
        />
      </Stack>
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Buy vs Sell Volume
          </Typography>
          <MetricInfo metric="buySellVolumeTrend" label="Buy vs Sell Volume trend" />
        </Stack>
        <Stack direction="row" spacing={0.5}>
          <Sparkline
            values={history.buyVolume}
            ariaLabel="Buy volume trend"
            color="var(--mui-palette-success-main)"
          />
          <Sparkline
            values={history.sellVolume}
            ariaLabel="Sell volume trend"
            color="var(--mui-palette-error-main)"
          />
        </Stack>
      </Stack>
      <StatTile
        label="Buy/Sell Imbalance"
        value={formatImbalance(rolling.buySellImbalance)}
        color={imbalanceColor(rolling.buySellImbalance)}
        adornment={<MetricInfo metric="buySellImbalance" label="Buy/Sell Imbalance" />}
      />
    </Box>
  );
}

export const RollingAnalyticsPanel = memo(RollingAnalyticsPanelInner);
