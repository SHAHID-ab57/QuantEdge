'use client';

import Box from '@mui/material/Box';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatNumber } from '@/features/markets/lib/format';
import type { SessionStats } from '../lib/session-stats';
import { BuySellPressureBar } from './buy-sell-pressure-bar';
import { MetricInfo } from './metric-info';

export interface StatsCardsProps {
  stats: SessionStats;
}

const UNAVAILABLE = 'Unavailable';

function orUnavailable(value: number | null, formatter: (value: number) => string): string {
  return value === null ? UNAVAILABLE : formatter(value);
}

/**
 * Session-wide totals: Buy Volume, Sell Volume, Total Volume, Buy/Sell
 * Ratio (plus a visual pressure bar alongside it), Average Trade Size, and
 * Number of Trades — every field derived from `SessionStats`
 * (`lib/session-stats.ts`), an O(1) running accumulation over every trade
 * since this page connected to the symbol, not a re-summed array.
 *
 * Every tile carries a `MetricInfo` button explaining the figure; the
 * session's largest trade has its own dedicated card (`LargestTradeCard`)
 * at the page level, and current price / high / low live in `PriceHeader`.
 * This component renders bare tiles rather than its own `Paper` — the page
 * wraps it in a `Section`, so it does not add a second border of its own.
 */
function StatsCardsInner({ stats }: StatsCardsProps) {
  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 3 }, alignItems: 'center' }}
      role="status"
      aria-label="Trade statistics"
    >
      <StatTile
        label="Buy Volume"
        value={formatNumber(stats.buyVolume)}
        color="success.main"
        adornment={<MetricInfo metric="buyVolume" label="Buy Volume" />}
      />
      <StatTile
        label="Sell Volume"
        value={formatNumber(stats.sellVolume)}
        color="error.main"
        adornment={<MetricInfo metric="sellVolume" label="Sell Volume" />}
      />
      <StatTile
        label="Total Volume"
        value={formatNumber(stats.totalVolume)}
        emphasis
        adornment={<MetricInfo metric="totalVolume" label="Total Volume" />}
      />
      <StatTile
        label="Buy/Sell Ratio"
        value={orUnavailable(stats.buySellRatio, (v) => v.toFixed(2))}
        adornment={<MetricInfo metric="buySellRatio" label="Buy/Sell Ratio" />}
      />
      <BuySellPressureBar
        label="Session Buy/Sell Volume"
        buyVolume={stats.buyVolume}
        sellVolume={stats.sellVolume}
        info={<MetricInfo metric="buySellPressure" label="Session Buy/Sell Pressure" />}
      />
      <StatTile
        label="Average Trade Size"
        value={orUnavailable(stats.avgTradeSize, formatNumber)}
        adornment={<MetricInfo metric="avgTradeSize" label="Average Trade Size" />}
      />
      <StatTile
        label="Number of Trades"
        value={formatNumber(stats.tradeCount)}
        adornment={<MetricInfo metric="tradeCount" label="Number of Trades" />}
      />
    </Box>
  );
}

export const StatsCards = memo(StatsCardsInner);
