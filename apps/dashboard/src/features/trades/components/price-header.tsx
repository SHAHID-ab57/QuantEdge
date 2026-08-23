'use client';

import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatPrice } from '@/features/markets/lib/format';
import type { SessionStats } from '../lib/session-stats';
import type { VwapDistance } from '../lib/vwap-distance';
import { MetricInfo } from './metric-info';

export interface PriceHeaderProps {
  symbol: string;
  stats: SessionStats;
  vwapDistance: VwapDistance | null;
  tradesPerSecond: number;
  isLive: boolean;
}

const UNAVAILABLE = 'Unavailable';

const SIDE_COLOR: Record<NonNullable<SessionStats['lastSide']>, string> = {
  buy: 'success.main',
  sell: 'error.main',
  unknown: 'text.primary',
};

function price(value: number | null): string {
  return value === null ? UNAVAILABLE : formatPrice(String(value));
}

function formatVwapDistance(distance: VwapDistance | null): string {
  if (distance === null) {
    return UNAVAILABLE;
  }
  const percent = (distance.fraction * 100).toFixed(2);
  return distance.fraction > 0 ? `+${percent}%` : `${percent}%`;
}

function vwapDistanceColor(distance: VwapDistance | null): string | undefined {
  if (distance === null || distance.fraction === 0) {
    return undefined;
  }
  return distance.fraction > 0 ? 'success.main' : 'error.main';
}

/**
 * The page's primary band: current price at the top of the type scale, with
 * the session range, VWAP distance, and a live-activity readout as
 * supporting figures beside it. Everything below this on the page is
 * deliberately a step down in visual weight — before this pass every panel
 * competed at the same size, which left a researcher with no entry point.
 *
 * The activity dot animates only while the stream is live *and* trades are
 * actually printing, so a frozen feed is visibly frozen rather than
 * pulsing reassuringly at a stale number.
 */
function PriceHeaderInner({
  symbol,
  stats,
  vwapDistance,
  tradesPerSecond,
  isLive,
}: PriceHeaderProps) {
  const active = isLive && tradesPerSecond > 0;
  let activityLabel = UNAVAILABLE;
  if (tradesPerSecond > 0) {
    activityLabel = `${tradesPerSecond.toFixed(1)}/s`;
  } else if (isLive) {
    // Connected but nothing printing: a real, meaningful state, distinct
    // from "we have no connection to report a rate from at all".
    activityLabel = 'Idle';
  }

  return (
    <Paper
      variant="outlined"
      role="status"
      aria-label={`${symbol} price summary`}
      sx={{
        p: { xs: 1.5, sm: 2 },
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: { xs: 2, sm: 3.5 },
        // A subtle top accent lifts the primary band above the sections
        // below it without resorting to a heavier border or a bright fill.
        borderTop: '2px solid',
        borderTopColor: active ? 'success.main' : 'divider',
        transition: 'border-top-color 300ms ease',
      }}
    >
      <Stack spacing={0.25} sx={{ minWidth: 190 }}>
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.4 }}>
            {symbol} · Current Price
          </Typography>
          <MetricInfo metric="currentPrice" label="Current Price" />
        </Stack>
        <Typography
          component="p"
          sx={{
            fontSize: { xs: '2rem', sm: '2.5rem' },
            fontWeight: 700,
            lineHeight: 1.1,
            fontVariantNumeric: 'tabular-nums',
            color:
              stats.lastPrice === null ? 'text.disabled' : SIDE_COLOR[stats.lastSide ?? 'unknown'],
          }}
        >
          {price(stats.lastPrice)}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap alignItems="center">
        <StatTile
          label="Session High"
          value={price(stats.sessionHigh)}
          color={stats.sessionHigh === null ? undefined : 'success.main'}
          adornment={<MetricInfo metric="sessionHigh" label="Session High" />}
        />
        <StatTile
          label="Session Low"
          value={price(stats.sessionLow)}
          color={stats.sessionLow === null ? undefined : 'error.main'}
          adornment={<MetricInfo metric="sessionLow" label="Session Low" />}
        />
        <StatTile
          label="vs VWAP"
          value={formatVwapDistance(vwapDistance)}
          color={vwapDistanceColor(vwapDistance)}
          caption={
            vwapDistance === null ? undefined : `${formatPrice(String(vwapDistance.absolute))} abs.`
          }
          adornment={<MetricInfo metric="vwapDistance" label="Distance from VWAP" />}
          minWidth={140}
        />
        <Stack spacing={0.25} sx={{ minWidth: 120 }}>
          <Stack direction="row" spacing={0.25} alignItems="center">
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
              Activity
            </Typography>
            <MetricInfo metric="tradesPerSecond" label="Trades per second" />
          </Stack>
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Box
              aria-hidden
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                flexShrink: 0,
                bgcolor: active ? 'success.main' : 'text.disabled',
                '@keyframes activityPulse': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0.25 },
                },
                ...(active && { animation: 'activityPulse 1.4s ease-in-out infinite' }),
              }}
            />
            <Typography
              component="p"
              sx={{
                fontWeight: 600,
                fontSize: '1.125rem',
                lineHeight: 1.25,
                fontVariantNumeric: 'tabular-nums',
                color: activityLabel === UNAVAILABLE ? 'text.disabled' : 'text.primary',
              }}
            >
              {activityLabel}
            </Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            trades / second
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}

export const PriceHeader = memo(PriceHeaderInner);
