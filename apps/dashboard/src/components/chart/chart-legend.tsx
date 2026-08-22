'use client';

import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { UTCTimestamp } from 'lightweight-charts';

export interface ChartLegendPoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface ChartLegendProps {
  point: ChartLegendPoint | null;
}

const priceFormatter = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
});
const volumeFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const timeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

function formatPrice(value: number): string {
  return priceFormatter.format(value);
}

interface LegendItemProps {
  label: string;
  value: string;
  color?: string;
}

function LegendItem({ label, value, color }: LegendItemProps) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="baseline">
      <Typography variant="caption" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography
        variant="caption"
        component="dd"
        sx={{ m: 0, fontWeight: 600, color: color ?? 'text.primary' }}
      >
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * Crosshair readout: Open/High/Low/Close/Volume/Timestamp (Objective #6).
 * Purely presentational — `ChartContainer` supplies `point` from
 * `CandlestickChart`'s `onCrosshairMove` callback, falling back to the most
 * recent candle when nothing is hovered.
 */
export function ChartLegend({ point }: ChartLegendProps) {
  if (!point) {
    return (
      <Typography variant="caption" color="text.secondary">
        Hover the chart for candle details.
      </Typography>
    );
  }

  const upColorSx = 'success.main';
  const downColorSx = 'error.main';
  const changeColor = point.close >= point.open ? upColorSx : downColorSx;

  return (
    <Stack
      component="dl"
      direction="row"
      spacing={2}
      alignItems="baseline"
      sx={{ m: 0, flexWrap: 'wrap', rowGap: 0.5 }}
      aria-label="Candle details at crosshair"
    >
      <LegendItem label="Time" value={timeFormatter.format(point.time * 1000)} />
      <LegendItem label="O" value={formatPrice(point.open)} color={changeColor} />
      <LegendItem label="H" value={formatPrice(point.high)} color={changeColor} />
      <LegendItem label="L" value={formatPrice(point.low)} color={changeColor} />
      <LegendItem label="C" value={formatPrice(point.close)} color={changeColor} />
      <LegendItem
        label="Vol"
        value={point.volume === null ? '—' : volumeFormatter.format(point.volume)}
      />
    </Stack>
  );
}
