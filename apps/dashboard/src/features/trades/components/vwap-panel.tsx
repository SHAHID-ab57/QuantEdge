'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatPrice } from '@/features/markets/lib/format';
import type { MetricHistory } from '../lib/metric-history';
import type { VwapSet } from '../lib/rolling-window';
import { MetricInfo } from './metric-info';
import { Sparkline } from './sparkline';

export interface VwapPanelProps {
  vwap: VwapSet;
  history: MetricHistory;
}

const UNAVAILABLE = 'Unavailable';

function vwapValue(value: number | null): string {
  return value === null ? UNAVAILABLE : formatPrice(String(value));
}

/**
 * Session VWAP and rolling 1m/5m/15m VWAP — all four derived from
 * `VwapSet` (`lib/rolling-window.ts`). "Session" means since this page
 * connected to the symbol, not the exchange's own trading-session
 * boundary — the platform has no historical trade log to reconstruct
 * that from (only OHLCV candles are stored). Rolling figures come from a
 * single time-pruned 15-minute buffer, not three separately-maintained
 * ones. The 1-minute VWAP also gets a trend sparkline
 * (`history.vwapOneMinute`, sampled roughly every 2 seconds — see
 * `lib/metric-history.ts`) since a single point can't show whether it's
 * been climbing or falling.
 *
 * Renders bare tiles; the page wraps it in a `Section` that supplies the
 * heading and border.
 */
function VwapPanelInner({ vwap, history }: VwapPanelProps) {
  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 3 }, alignItems: 'center' }}
      role="status"
      aria-label="VWAP"
    >
      <StatTile
        label="Session VWAP"
        value={vwapValue(vwap.session)}
        emphasis
        adornment={<MetricInfo metric="sessionVwap" label="Session VWAP" />}
      />
      <Stack spacing={0.5}>
        <StatTile
          label="1m VWAP"
          value={vwapValue(vwap.oneMinute)}
          adornment={<MetricInfo metric="rollingVwap" label="1-minute VWAP" />}
        />
        <Sparkline
          values={history.vwapOneMinute}
          ariaLabel="Rolling 1-minute VWAP trend"
          color="var(--mui-palette-info-main)"
        />
      </Stack>
      <StatTile
        label="5m VWAP"
        value={vwapValue(vwap.fiveMinute)}
        adornment={<MetricInfo metric="rollingVwap" label="5-minute VWAP" />}
      />
      <StatTile
        label="15m VWAP"
        value={vwapValue(vwap.fifteenMinute)}
        adornment={<MetricInfo metric="rollingVwap" label="15-minute VWAP" />}
      />
    </Box>
  );
}

export const VwapPanel = memo(VwapPanelInner);
