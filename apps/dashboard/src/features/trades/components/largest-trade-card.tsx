'use client';

import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatNumber, formatPrice } from '@/features/markets/lib/format';
import type { TradeRecord } from '../lib/trade-record';
import { MetricInfo } from './metric-info';

export interface LargestTradeCardProps {
  title: string;
  trade: TradeRecord | null;
}

const UNAVAILABLE = 'Unavailable';

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const SIDE_COLOR: Record<TradeRecord['side'], string> = {
  buy: 'success.main',
  sell: 'error.main',
  unknown: 'text.secondary',
};

const SIDE_LABEL: Record<TradeRecord['side'], string> = {
  buy: 'Buy',
  sell: 'Sell',
  unknown: 'Unknown',
};

/**
 * A dedicated "largest trade" card — Time, Side, Price, Quantity, and
 * Value all shown explicitly, rather than the single value-plus-caption
 * `StatTile` this replaced in `StatsCards`/`RollingAnalyticsPanel`. Used
 * for both the session-wide largest trade and the trailing one-minute
 * largest trade (same shape, different `title`/`trade`), so a researcher
 * can see at a glance whether the biggest print happened just now or
 * earlier in the session.
 */
function LargestTradeCardInner({ title, trade }: LargestTradeCardProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.75,
        flex: '1 1 280px',
        borderColor: 'divider',
        transition: 'border-color 200ms ease, background-color 200ms ease',
        '&:hover': {
          borderColor: 'rgba(148, 163, 184, 0.32)',
          bgcolor: 'rgba(148, 163, 184, 0.03)',
        },
      }}
    >
      <Stack direction="row" spacing={0.25} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        <MetricInfo metric="largestTrade" label={title} />
      </Stack>
      {trade === null ? (
        <Typography variant="body2" color="text.disabled">
          {UNAVAILABLE}
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
          <StatTile
            label="Time"
            value={timeFormatter.format(new Date(trade.timestampMs))}
            minWidth={84}
          />
          <StatTile
            label="Side"
            value={SIDE_LABEL[trade.side]}
            color={SIDE_COLOR[trade.side]}
            minWidth={56}
          />
          <StatTile label="Price" value={formatPrice(String(trade.price))} minWidth={84} />
          <StatTile label="Quantity" value={formatNumber(trade.size)} minWidth={72} />
          <StatTile
            label="Value"
            value={formatPrice(String(trade.value))}
            emphasis
            minWidth={100}
          />
        </Box>
      )}
    </Paper>
  );
}

export const LargestTradeCard = memo(LargestTradeCardInner);
