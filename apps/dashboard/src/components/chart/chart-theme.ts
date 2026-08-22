import type { Theme } from '@mui/material/styles';
import {
  ColorType,
  CrosshairMode,
  type ChartOptions,
  type DeepPartial,
  type HistogramSeriesPartialOptions,
  type CandlestickSeriesPartialOptions,
} from 'lightweight-charts';

/**
 * Derives lightweight-charts option objects from the active MUI theme so the
 * chart never introduces a second, parallel theming system (Objective #7).
 * Call sites re-invoke these builders whenever the MUI theme changes and pass
 * the result to `chart.applyOptions()` / `series.applyOptions()`.
 */

export function buildChartOptions(theme: Theme): DeepPartial<ChartOptions> {
  const palette = theme.palette;
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: palette.text.secondary,
      fontFamily: theme.typography.fontFamily,
      panes: {
        separatorColor: palette.divider,
      },
    },
    grid: {
      vertLines: { color: palette.divider },
      horzLines: { color: palette.divider },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: palette.text.secondary, labelBackgroundColor: palette.background.paper },
      horzLine: { color: palette.text.secondary, labelBackgroundColor: palette.background.paper },
    },
    rightPriceScale: {
      borderColor: palette.divider,
    },
    timeScale: {
      borderColor: palette.divider,
      timeVisible: true,
      secondsVisible: false,
    },
  };
}

export function buildCandlestickSeriesOptions(theme: Theme): CandlestickSeriesPartialOptions {
  const palette = theme.palette;
  return {
    upColor: palette.success.main,
    downColor: palette.error.main,
    borderUpColor: palette.success.main,
    borderDownColor: palette.error.main,
    wickUpColor: palette.success.main,
    wickDownColor: palette.error.main,
  };
}

export function buildVolumeSeriesOptions(): HistogramSeriesPartialOptions {
  return {
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  };
}

/** Overlay margins that keep the volume histogram in the bottom of the pane. */
export const VOLUME_SCALE_MARGINS = { top: 0.82, bottom: 0 };
