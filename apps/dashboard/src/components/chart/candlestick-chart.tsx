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
  /**
   * When set, the chart opens focused on the most recent `initialVisibleBars`
   * bars (with a little empty space on the right for the forming bar to grow
   * into) instead of fitting the whole dataset. The Live Market Dashboard
   * passes this so a live-updating last candle is actually visible rather
   * than a sub-pixel sliver of a fully zoomed-out multi-month history; the
   * "Fit Content" toolbar button still shows everything on demand. Omit for
   * a research chart that should open showing its full range (the History
   * page). No effect when the dataset has fewer bars than this.
   */
  initialVisibleBars?: number;
  /**
   * When provided, the initial view (a full fit, or the `initialVisibleBars`
   * recent window) is applied on mount and re-applied only when this key
   * changes — a data change that arrives without a key change (a periodic
   * historical refetch on a live chart) then just updates the bars and
   * leaves the viewer's current pan/zoom untouched. Omit for a
   * manually-refreshed research chart, where every data change re-applies
   * the fit.
   */
  viewResetKey?: string | number;
  height?: number;
}

/** Sentinel for `appliedViewKeyRef` — "the initial view has not been applied to this chart yet". */
const VIEW_NOT_APPLIED = Symbol('view-not-applied');

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
  initialVisibleBars,
  viewResetKey,
  height = 480,
}: CandlestickChartProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  /** Newest time pushed into the series, guarding out-of-order live updates. */
  const lastPushedTimeRef = useRef<number>(Number.NEGATIVE_INFINITY);
  /**
   * The `fitContentToken` value the fit-on-demand effect last acted on, so
   * that effect fits only on a genuine change (a toolbar click) and never on
   * its mount pass — which, once `initialVisibleBars` is in play, would
   * immediately undo the recent-window view the data effect just set.
   */
  const actedFitTokenRef = useRef(fitContentToken);
  /**
   * The `viewResetKey` the initial view was last applied for (see that
   * prop). Starts at the `VIEW_NOT_APPLIED` sentinel — distinct from a
   * caller's `viewResetKey={undefined}` — and is reset back to it when the
   * chart is recreated, so a fresh chart re-applies its initial view.
   */
  const appliedViewKeyRef = useRef<string | number | undefined | typeof VIEW_NOT_APPLIED>(
    VIEW_NOT_APPLIED,
  );
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
      lastPushedTimeRef.current = Number.NEGATIVE_INFINITY;
      // A recreated chart (React StrictMode's mount/unmount/remount) has no
      // view set — let the data effect re-apply the initial framing on the
      // new chart instead of treating it as "already done".
      appliedViewKeyRef.current = VIEW_NOT_APPLIED;
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
    const timeScale = chartRef.current?.timeScale();
    if (!timeScale || candlesticks.length === 0) {
      return;
    }
    // With a `viewResetKey`, apply the initial view once per key — a periodic
    // refetch (same key, fresh bars) then leaves the viewer's pan/zoom alone,
    // since `setData` on its own never resets the time scale. Without one,
    // every data change re-fits (a manually-refreshed research chart).
    if (viewResetKey !== undefined && appliedViewKeyRef.current === viewResetKey) {
      return;
    }
    appliedViewKeyRef.current = viewResetKey;
    if (initialVisibleBars && candlesticks.length > initialVisibleBars) {
      // Open on the most recent window, leaving a few bar-widths of empty
      // space on the right so the live forming bar has somewhere to grow.
      // New bars appended later via `series.update()` keep the right edge in
      // view (lightweight-charts' `shiftVisibleRangeOnNewBar`, on by default).
      const rightMargin = Math.max(2, Math.round(initialVisibleBars * 0.06));
      timeScale.setVisibleLogicalRange({
        from: candlesticks.length - initialVisibleBars,
        to: candlesticks.length - 1 + rightMargin,
      });
    } else {
      timeScale.fitContent();
    }
  }, [candlesticks, volume, initialVisibleBars, viewResetKey]);

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
  // without re-pushing data. Fits only when the token actually changed —
  // never on the mount pass (or React StrictMode's second one), which the
  // `setData` effect above has already framed (a full fit, or — with
  // `initialVisibleBars` — a recent window a stray `fitContent()` would
  // immediately undo).
  useEffect(() => {
    if (actedFitTokenRef.current === fitContentToken) {
      return;
    }
    actedFitTokenRef.current = fitContentToken;
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
