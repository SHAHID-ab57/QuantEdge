'use client';

import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import {
  formatDateTime,
  formatNumber,
  formatPrice,
  formatRelative,
} from '@/features/markets/lib/format';
import type { LiveFundingData, LiveTickerData, LiveTradeData } from '@/types/api/market-stream';
import { total24hVolume } from '../hooks/use-price-stats';

/**
 * Rendered wherever a value genuinely isn't known, instead of a dash or a
 * zero. A quantitative user reading a price card must be able to tell
 * "nothing has arrived" apart from "the value is 0".
 */
export const UNAVAILABLE = 'Unavailable';

export interface PriceStats24h {
  highestPrice: string | null;
  lowestPrice: string | null;
  averageVolume: string | null;
  totalCandles: number;
  lastCandleAt: string | null;
}

export interface PriceCardProps {
  symbol: string;
  latestTrade: LiveTradeData | null;
  latestTicker: LiveTickerData | null;
  latestFunding: LiveFundingData | null;
  stats: PriceStats24h | undefined;
  statsLoading: boolean;
  statsError: boolean;
  now: number;
}

function currentPrice(trade: LiveTradeData | null, ticker: LiveTickerData | null): string | null {
  return ticker?.last_price ?? trade?.price ?? null;
}

function changeColor(changeValue: number | null): string | undefined {
  if (changeValue === null) {
    return undefined;
  }
  return changeValue >= 0 ? 'success.main' : 'error.main';
}

function formatChange(changeValue: number | null): string {
  if (changeValue === null) {
    return UNAVAILABLE;
  }
  return `${changeValue >= 0 ? '+' : ''}${changeValue.toFixed(2)}%`;
}

/** `formatPrice`/`formatNumber` render a dash for missing values; say so explicitly instead. */
function orUnavailable(formatted: string): string {
  return formatted === '—' ? UNAVAILABLE : formatted;
}

/**
 * `funding_rate` is a signed fraction per funding interval (e.g. `-0.000116`
 * = shorts pay longs 0.0116% this interval); render it as a percentage with
 * enough precision to be meaningful at that scale.
 */
function formatFundingRate(rate: string | null | undefined): string {
  if (rate === null || rate === undefined) {
    return UNAVAILABLE;
  }
  const value = Number(rate);
  if (!Number.isFinite(value)) {
    return UNAVAILABLE;
  }
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(4)}%`;
}

function fundingIntervalLabel(seconds: number | null | undefined): string | undefined {
  if (!seconds || seconds <= 0) {
    return undefined;
  }
  const hours = seconds / 3600;
  return Number.isInteger(hours) ? `every ${hours}h` : `every ${Math.round(seconds / 60)}m`;
}

interface StatProps {
  label: string;
  value: string;
  color?: string;
  hint?: string;
  emphasis?: boolean;
  /** Secondary line, e.g. how long ago a timestamp was. */
  caption?: string;
}

function Stat({ label, value, color, hint, emphasis = false, caption }: StatProps) {
  const body = (
    <Stack spacing={0.25} sx={{ minWidth: 140 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography
        variant={emphasis ? 'h5' : 'h6'}
        component="p"
        sx={{
          fontWeight: 600,
          color: color ?? (value === UNAVAILABLE ? 'text.disabled' : 'text.primary'),
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </Typography>
      {caption ? (
        <Typography variant="caption" color="text.secondary">
          {caption}
        </Typography>
      ) : null}
    </Stack>
  );
  return hint ? <Tooltip title={hint}>{body}</Tooltip> : body;
}

/**
 * Current price and 24h change come from the live WebSocket ticker (falling
 * back to the most recent trade); 24h high/low/volume are derived from
 * *stored* candles via the existing `/candles/stats` endpoint, which is why
 * they carry a tooltip saying so — they track the platform's own synced
 * history, and will read low if candle sync has fallen behind.
 */
function PriceCardInner({
  symbol,
  latestTrade,
  latestTicker,
  latestFunding,
  stats,
  statsLoading,
  statsError,
  now,
}: PriceCardProps) {
  const price = currentPrice(latestTrade, latestTicker);
  const change = latestTicker?.price_change_24h ?? null;
  const parsedChange = change === null ? null : Number(change);
  const changeValue = parsedChange !== null && Number.isFinite(parsedChange) ? parsedChange : null;
  const volume = stats ? total24hVolume(stats.averageVolume, stats.totalCandles) : null;

  const storedHint = 'Derived from candles stored by this platform, not from the exchange ticker.';

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label={`${symbol} live price`}>
      <Typography variant="h6" component="h2" gutterBottom>
        {symbol}
      </Typography>
      <Stack direction="row" spacing={3} useFlexGap sx={{ flexWrap: 'wrap' }}>
        <Stat
          label="Current Price"
          value={orUnavailable(formatPrice(price))}
          emphasis
          hint="Latest ticker price, or the most recent trade before the first ticker arrives."
        />
        <Stat
          label="24h Change"
          value={formatChange(changeValue)}
          color={changeColor(changeValue)}
          hint="Reported by the exchange ticker."
        />
        {statsLoading && !stats ? (
          <Skeleton variant="text" width={280} aria-label="Loading 24 hour statistics" />
        ) : (
          <>
            <Stat
              label="24h High"
              value={statsError ? UNAVAILABLE : orUnavailable(formatPrice(stats?.highestPrice))}
              hint={storedHint}
            />
            <Stat
              label="24h Low"
              value={statsError ? UNAVAILABLE : orUnavailable(formatPrice(stats?.lowestPrice))}
              hint={storedHint}
            />
            <Stat
              label="24h Volume"
              value={statsError || volume === null ? UNAVAILABLE : formatNumber(volume)}
              hint={storedHint}
            />
          </>
        )}
        <Stat
          label="Open Interest"
          value={orUnavailable(formatPrice(latestTicker?.open_interest ?? null))}
          hint="Open interest reported by the exchange ticker."
        />
        <Stat
          label="Funding Rate"
          value={formatFundingRate(latestFunding?.funding_rate)}
          color={latestFunding ? changeColor(Number(latestFunding.funding_rate)) : undefined}
          caption={
            latestFunding
              ? [
                  fundingIntervalLabel(latestFunding.funding_interval_seconds),
                  latestFunding.next_funding_time
                    ? `next ${formatRelative(latestFunding.next_funding_time, now)}`
                    : undefined,
                ]
                  .filter(Boolean)
                  .join(' · ') || undefined
              : undefined
          }
          hint="Perpetual funding rate for the current interval (positive: longs pay shorts). Funding frames are infrequent, so this can lag a fresh connection."
        />
        <Stat
          label="Last Trade Time"
          value={latestTrade ? formatDateTime(latestTrade.event_time) : UNAVAILABLE}
          caption={latestTrade ? formatRelative(latestTrade.event_time, now) : undefined}
          hint="Exchange timestamp of the most recent streamed trade."
        />
        <Stat
          label="Last Candle Time"
          value={
            statsError || !stats?.lastCandleAt ? UNAVAILABLE : formatDateTime(stats.lastCandleAt)
          }
          caption={
            !statsError && stats?.lastCandleAt ? formatRelative(stats.lastCandleAt, now) : undefined
          }
          hint="Open time of the newest candle stored for this market."
        />
      </Stack>
    </Paper>
  );
}

export const PriceCard = memo(PriceCardInner);
