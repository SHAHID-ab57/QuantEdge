'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTheme, type Theme } from '@mui/material/styles';
import { memo, useMemo } from 'react';
import { buildLinePath, computeDomain, yForValue } from '@/lib/svg-line-path';
import type { IndicatorSeries } from '@/types/api/indicators';
import type { ChartConfig } from '../lib/indicator-knowledge';

export interface IndicatorChartProps {
  series: readonly IndicatorSeries[];
  config: ChartConfig;
  height?: number;
}

const WIDTH = 640;
const DEFAULT_HEIGHT = 160;
const SERIES_COLOR_KEYS = ['primary', 'secondary', 'warning', 'success'] as const;

function seriesColor(theme: Theme, index: number): string {
  const key = SERIES_COLOR_KEYS[index % SERIES_COLOR_KEYS.length]!;
  return theme.palette[key].main;
}

/**
 * Neutral, non-evaluative colors for a reference line's band position —
 * deliberately not success/error (green/red), which this codebase reserves
 * for "good/bad" and would read as a buy/sell cue on a line that is purely
 * describing where a threshold sits on the oscillator's scale.
 */
function referenceLineColor(theme: Theme, band: 'low' | 'mid' | 'high'): string {
  if (band === 'low') return theme.palette.info.main;
  if (band === 'high') return theme.palette.warning.main;
  return theme.palette.divider;
}

/**
 * A small, dependency-free multi-line visualization of one calculation's
 * output series — deliberately not a second `lightweight-charts` instance.
 * It reuses the exact same SVG path math as the Trade Analytics
 * `Sparkline` (`@/lib/svg-line-path`), extended for multiple series
 * sharing one y-scale and for an oscillator's optional fixed domain and
 * reference lines (RSI's 30/50/70).
 *
 * Driven entirely by `config` from the indicator knowledge base (never a
 * switch on the indicator's name), so a future oscillator or multi-series
 * indicator (MACD, Bollinger Bands) renders correctly here the moment it
 * declares a `ChartConfig` — no change to this component.
 */
function IndicatorChartInner({ series, config, height = DEFAULT_HEIGHT }: IndicatorChartProps) {
  const theme = useTheme();

  const domain = useMemo(() => {
    if (config.domain) {
      return { min: config.domain[0], max: config.domain[1] };
    }
    const extra = config.referenceLines?.map((line) => line.value) ?? [];
    return (
      computeDomain(
        series.map((entry) => entry.values),
        extra,
      ) ?? { min: 0, max: 1 }
    );
  }, [series, config.domain, config.referenceLines]);

  const paths = useMemo(
    () =>
      series.map((entry, index) => ({
        name: entry.name,
        label: entry.label,
        color: seriesColor(theme, index),
        path: buildLinePath(entry.values, WIDTH, height, domain),
      })),
    [series, domain, height, theme],
  );

  const hasAnyPath = paths.some((entry) => entry.path !== null);
  const ariaLabel = `${series.map((entry) => entry.label).join(', ')} chart`;

  return (
    <Box>
      <Box
        component="svg"
        width="100%"
        height={height}
        viewBox={`0 0 ${WIDTH} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={ariaLabel}
      >
        {config.referenceLines?.map((line) => {
          const y = yForValue(line.value, height, domain);
          return (
            <line
              key={line.value}
              x1={0}
              x2={WIDTH}
              y1={y}
              y2={y}
              stroke={referenceLineColor(theme, line.band)}
              strokeDasharray="4 4"
              strokeWidth={1}
            />
          );
        })}
        {paths.map((entry) =>
          entry.path ? (
            <path
              key={entry.name}
              d={entry.path}
              fill="none"
              stroke={entry.color}
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null,
        )}
      </Box>

      {!hasAnyPath ? (
        <Typography variant="caption" color="text.secondary">
          Not enough data to draw a chart yet.
        </Typography>
      ) : null}

      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
        {paths.map((entry) => (
          <Stack key={entry.name} direction="row" spacing={0.5} alignItems="center">
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: entry.color }} />
            <Typography variant="caption" color="text.secondary">
              {entry.label}
            </Typography>
          </Stack>
        ))}
        {config.referenceLines?.map((line) => (
          <Stack key={line.value} direction="row" spacing={0.5} alignItems="center">
            <Box
              sx={{
                width: 10,
                height: 0,
                borderTop: '2px dashed',
                borderColor: referenceLineColor(theme, line.band),
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {line.label}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

export const IndicatorChart = memo(IndicatorChartInner);
