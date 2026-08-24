'use client';

import Box from '@mui/material/Box';
import { useTheme } from '@mui/material/styles';
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
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

/**
 * One indicator overlay's line series — the Overlay Engine's unit of
 * rendering. `id` identifies the series across renders so it can be
 * created once and updated in place rather than torn down and rebuilt
 * (see the reconciliation effect below); `data` should be referentially
 * stable across renders where the underlying values haven't changed, the
 * same discipline `candlesticks`/`volume` already require, so an overlay
 * whose values are unchanged never re-pushes into the chart.
 */
export interface OverlaySeriesInput {
  id: string;
  label: string;
  color: string;
  data: LineData[];
}

export interface CandlestickChartProps {
  candlesticks: CandlestickData[];
  volume: HistogramData[];
  /** Called with the hovered point, or `null` when the crosshair leaves the chart. */
  onCrosshairMove?: (point: CrosshairPoint | null) => void;
  /** Bump this (e.g. on every button click) to force `timeScale().fitContent()` on demand. */
  fitContentToken?: number;
  /**
   * The currently-forming bar, pushed via `series.update()` instead of a
   * full `setData()` (Live Market Dashboard: Objective "append new
   * candles in real time... avoid full chart re-renders"). Must have a
   * `time` at or after the last point in `candlesticks`; omit/pass `null`
   * for a purely historical chart (e.g. the History page).
   */
  liveCandle?: CandlestickData | null;
  liveVolume?: HistogramData | null;
  /**
   * Indicator overlays (SMA/EMA/WMA lines, etc.) sharing this chart's
   * price scale — see the Indicator Management & Chart Overlay System
   * (`src/features/indicator-overlays/`). Each is rendered as its own
   * `LineSeries`, reconciled by `id` against the previous render rather
   * than rebuilding the whole chart; omit for a chart with no overlays.
   */
  overlays?: OverlaySeriesInput[];
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
  liveCandle = null,
  liveVolume = null,
  overlays = [],
  height = 480,
}: CandlestickChartProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  /** Newest time pushed into the series, guarding out-of-order live updates. */
  const lastPushedTimeRef = useRef<number>(Number.NEGATIVE_INFINITY);
  /** One `LineSeries` per overlay `id`, created once and updated in place. */
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  /** The `data` reference last pushed per overlay `id`, so an unchanged overlay is never re-pushed. */
  const overlayDataRef = useRef<Map<string, LineData[]>>(new Map());
  /** The overlay id order last synced to the chart, to detect a pure reorder (see below). */
  const overlayOrderRef = useRef<string[]>([]);

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
    const overlaySeriesById = overlaySeriesRef.current;
    const overlayDataById = overlayDataRef.current;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      // `chart.remove()` already disposes every series it owns, including
      // the overlay lines below — only this component's own bookkeeping
      // needs clearing so a remount never reuses a disposed series.
      overlaySeriesById.clear();
      overlayDataById.clear();
      overlayOrderRef.current = [];
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
    lastPushedTimeRef.current = Number(candlesticks.at(-1)?.time ?? Number.NEGATIVE_INFINITY);
    if (candlesticks.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [candlesticks, volume]);

  // The Overlay Engine: reconciles `overlays` against the series already on
  // the chart by `id` — create a `LineSeries` the first time an id appears,
  // remove it when the id disappears (the indicator was removed or
  // disabled), and otherwise leave an existing series alone. This is the
  // same "never rebuild the chart, only update what changed" discipline the
  // candle/volume series above already follow, extended to an arbitrary
  // number of simultaneously-rendered indicators.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) {
      return;
    }
    const seriesById = overlaySeriesRef.current;
    const dataById = overlayDataRef.current;
    const incomingIds = overlays.map((overlay) => overlay.id);
    const previousOrder = overlayOrderRef.current;

    // A pure reorder — the same set of overlay ids as last time, just in a
    // different sequence — can't be expressed as a per-series update:
    // lightweight-charts paints series in the order they were *added* to
    // the chart, so the Indicator Legend's drag-and-drop/up-down reorder
    // (which only ever changes this array's order) requires recreating
    // every series in the new order to make paint order actually follow
    // it. This only happens on an explicit reorder, never on an unrelated
    // add/remove/toggle, so it doesn't undermine "skip unrelated redraws"
    // below — a reorder redrawing everything is the correct, unavoidable
    // cost of a reorder.
    const sameMembership =
      incomingIds.length === previousOrder.length &&
      incomingIds.every((id) => previousOrder.includes(id));
    const orderChanged =
      sameMembership && incomingIds.some((id, index) => previousOrder[index] !== id);

    if (orderChanged) {
      for (const series of seriesById.values()) {
        chart.removeSeries(series);
      }
      seriesById.clear();
      dataById.clear();
    } else {
      for (const [id, series] of seriesById) {
        if (!incomingIds.includes(id)) {
          chart.removeSeries(series);
          seriesById.delete(id);
          dataById.delete(id);
        }
      }
    }

    for (const overlay of overlays) {
      let series = seriesById.get(overlay.id);
      if (!series) {
        series = chart.addSeries(LineSeries, {
          color: overlay.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          title: overlay.label,
        });
        seriesById.set(overlay.id, series);
      } else {
        series.applyOptions({ color: overlay.color, title: overlay.label });
      }
      // Skip the redraw entirely when this overlay's data hasn't actually
      // changed since the last push — the effect still runs whenever any
      // *other* overlay is added/removed/toggled (the whole `overlays`
      // array is a new reference then), but an unrelated overlay's line
      // must not be re-pushed just because a sibling changed.
      if (dataById.get(overlay.id) !== overlay.data) {
        series.setData(overlay.data);
        dataById.set(overlay.id, overlay.data);
      }
    }

    overlayOrderRef.current = incomingIds;
  }, [overlays]);

  // Lets a parent (e.g. a toolbar "Fit Content" button) re-fit on demand
  // without re-pushing data. Runs on mount too, which is harmless.
  useEffect(() => {
    chartRef.current?.timeScale().fitContent();
  }, [fitContentToken]);

  // Declared after the setData effect so a live update always wins the
  // leading edge over a (possibly slightly stale) historical refetch that
  // resolves in the same render pass.
  //
  // lightweight-charts throws if `update()` is called with a time before the
  // series' last point, which is reachable in normal operation: a historical
  // refetch can land while a forming bar for an *earlier* bucket is still on
  // screen. Dropping those updates keeps the chart on its newest data instead
  // of crashing the page.
  useEffect(() => {
    const liveTime = Number(liveCandle?.time ?? liveVolume?.time ?? Number.NEGATIVE_INFINITY);
    if (liveTime < lastPushedTimeRef.current) {
      return;
    }
    if (liveCandle) {
      candleSeriesRef.current?.update(liveCandle);
    }
    if (liveVolume) {
      volumeSeriesRef.current?.update(liveVolume);
    }
    lastPushedTimeRef.current = liveTime;
  }, [liveCandle, liveVolume]);

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
