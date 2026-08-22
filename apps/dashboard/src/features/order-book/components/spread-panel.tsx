'use client';

import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { formatPrice } from '@/features/markets/lib/format';
import type { SpreadSummary } from '../lib/order-book-depth';

export interface SpreadPanelProps {
  spread: SpreadSummary;
}

/** Renders "Unavailable" instead of a dash, matching the Live Market Dashboard's convention. */
const UNAVAILABLE = 'Unavailable';

function priceOrUnavailable(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  const formatted = formatPrice(String(value));
  return formatted === '—' ? UNAVAILABLE : formatted;
}

function formatSpreadPercent(value: number | null): string {
  if (value === null) {
    return UNAVAILABLE;
  }
  return `${value.toFixed(3)}%`;
}

interface StatProps {
  label: string;
  value: string;
}

function Stat({ label, value }: StatProps) {
  return (
    <Stack spacing={0.25} alignItems="center" sx={{ minWidth: 110 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant="h6"
        component="p"
        sx={{
          fontWeight: 600,
          fontVariantNumeric: 'tabular-nums',
          color: value === UNAVAILABLE ? 'text.disabled' : 'text.primary',
        }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * Best bid, best ask, spread, spread%, and mid price — the summary strip
 * between the two depth tables. Updates on every order-book tick; kept
 * `React.memo`-wrapped so it only re-renders when the spread numbers
 * themselves change, not on an unrelated parent re-render.
 */
function SpreadPanelInner({ spread }: SpreadPanelProps) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 3 }}
      role="status"
      aria-label="Order book spread"
    >
      <Stat label="Best Bid" value={priceOrUnavailable(spread.bestBid)} />
      <Stat label="Spread" value={priceOrUnavailable(spread.spread)} />
      <Stat label="Best Ask" value={priceOrUnavailable(spread.bestAsk)} />
      <Stat label="Spread %" value={formatSpreadPercent(spread.spreadPercent)} />
      <Stat label="Mid Price" value={priceOrUnavailable(spread.midPrice)} />
    </Paper>
  );
}

export const SpreadPanel = memo(SpreadPanelInner);
