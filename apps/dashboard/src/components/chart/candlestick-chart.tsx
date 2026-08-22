'use client';

import Box from '@mui/material/Box';
import { useTheme } from '@mui/material/styles';
import {
  CandlestickSeries,
  HistogramSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type UTCTimestamp,
} from 'lightweight-charts';
import { memo, useEffect, useRef } from 'react';
import {
  VOLUME_SCALE_MARGINS,
  buildCandlestickSeriesOptions,
  buildChartOptions,
  buildVolumeSeriesOptions,
} from './chart-theme';

export interface CrosshairPoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface CandlestickChartProps {
  candlesticks: CandlestickData[];
  volume: HistogramData[];
  /** Called with the hovered point, or `null` when the crosshair leaves the chart. */
  onCrosshairMove?: (point: CrosshairPoint | null) => void;
  /** Bump this (e.g. on every button click) to force `timeScale().fitContent()` on demand. */
  fitContentToken?: number;
  height?: number;
}

/**
 * This chart only ever plots numeric UTC-second candles (never business-day
 * or string time points — see `data-adapter.ts`), so it is safe to narrow
 * lightweight-charts' generic `Time` back down to our own `UTCTimestamp`
 * contract at the one point data crosses back out of the library.
 */
function readCrosshairPoint(
  param: MouseEventParams,
  candleSeries: ISeriesApi<'Candlestick'>,
  volumeSeries: ISeriesApi<'Histogram'>,
): CrosshairPoint | null {
  if (param.time === undefined) {
    return null;
  }
  const ohlc = param.seriesData.get(candleSeries) as CandlestickData | undefined;
  if (!ohlc) {
    return null;
  }
  const bar = param.seriesData.get(volumeSeries) as HistogramData | undefined;
  return {
    time: param.time as UTCTimestamp,
    open: ohlc.open,
    high: ohlc.high,
    low: ohlc.low,
    close: ohlc.close,
    volume: bar?.value ?? null,
  };
}

/**
 * Thin, imperative wrapper around TradingView's lightweight-charts
 * (Objective: "Use TradingView Lightweight Charts. Do NOT use any other
 * chart library"). lightweight-charts owns a `<canvas>` outside React's
 * render cycle, so this component only ever talks to it from `useEffect`s
 * keyed on the data/theme that actually changed — never on every render —
 * which is what keeps large datasets smooth (Objective #8).
 *
 * `React.memo`-wrapped: parents should pass memoized `candlesticks`/`volume`
 * arrays (see `ChartContainer`) so an unrelated parent re-render doesn't
 * force a data re-push into the chart.
 */
function CandlestickChartInner({
  candlesticks,
  volume,
  onCrosshairMove,
  fitContentToken = 0,
  height = 480,
}: CandlestickChartProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Create the chart once per mount. Theme changes are applied in-place by
  // the effect below rather than tearing the chart down and rebuilding it.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const chart = createChart(container, buildChartOptions(theme));
    const candleSeries = chart.addSeries(CandlestickSeries, buildCandlestickSeriesOptions(theme));
    const volumeSeries = chart.addSeries(HistogramSeries, buildVolumeSeriesOptions());
    volumeSeries.priceScale().applyOptions({ scaleMargins: VOLUME_SCALE_MARGINS });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
    // Intentionally created once; the theme-sync effect below keeps colors
    // current without recreating the chart on every theme/palette change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!chart || !candleSeries) {
      return;
    }
    chart.applyOptions(buildChartOptions(theme));
    candleSeries.applyOptions(buildCandlestickSeriesOptions(theme));
  }, [theme]);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !volumeSeries) {
      return;
    }
    candleSeries.setData(candlesticks);
    volumeSeries.setData(volume);
    if (candlesticks.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [candlesticks, volume]);

  // Lets a parent (e.g. a toolbar "Fit Content" button) re-fit on demand
  // without re-pushing data. Runs on mount too, which is harmless.
  useEffect(() => {
    chartRef.current?.timeScale().fitContent();
  }, [fitContentToken]);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries || !onCrosshairMove) {
      return undefined;
    }
    const handler = (param: MouseEventParams) => {
      onCrosshairMove(readCrosshairPoint(param, candleSeries, volumeSeries));
    };
    chart.subscribeCrosshairMove(handler);
    return () => chart.unsubscribeCrosshairMove(handler);
  }, [onCrosshairMove]);

  return (
    <Box
      ref={containerRef}
      role="img"
      aria-label="Historical candlestick price chart"
      sx={{ width: '100%', height }}
    />
  );
}

export const CandlestickChart = memo(CandlestickChartInner);
