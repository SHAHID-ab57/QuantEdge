import type { LineData } from 'lightweight-charts';
import { toUnixTime } from '@/components/chart/data-adapter';
import type { IndicatorBatchItemResult, IndicatorBatchResponse } from '@/types/api/indicators';
import type { OverlayConfig } from '../store/use-overlay-store';

/**
 * How one overlay's currently-displayed series was produced — Calculation
 * Time, Cache Status, Dataset Size, Warmup Period, Engine Version, and
 * Source Price, surfaced in the Indicator Panel/Legend's "Details" tooltip.
 * `candlesAnalyzed`/`generatedAt`/`engineVersion` are shared by the whole
 * batch (one candle load, one engine); `cacheStatus`/`warmupCandles`/
 * `executionTimeMs` are this overlay's own, since each indicator in a
 * batch still runs (and caches) independently.
 */
export interface OverlayResultMeta {
  cacheStatus: string | null;
  warmupCandles: number | null;
  executionTimeMs: number | null;
  candlesAnalyzed: number;
  generatedAt: string;
  engineVersion: string;
  /** The resolved `source` parameter (e.g. "close"), when the indicator declares one. */
  sourceParam: string | null;
}

export interface OverlayChartSeries {
  id: string;
  label: string;
  color: string;
  data: LineData[];
  /** `false` when the batch reported an error for this overlay — its line is simply absent from the chart. */
  ok: boolean;
  error?: string;
  meta?: OverlayResultMeta;
}

function sourceParamOf(result: IndicatorBatchItemResult | undefined): string | null {
  const source = result?.parameters?.['source'];
  return typeof source === 'string' ? source : null;
}

function metaFor(
  response: IndicatorBatchResponse,
  result: IndicatorBatchItemResult | undefined,
): OverlayResultMeta {
  return {
    cacheStatus: result?.cache_status ?? null,
    warmupCandles: result?.warmup_candles ?? null,
    executionTimeMs: result?.execution_time_ms ?? null,
    candlesAnalyzed: response.candles_analyzed,
    generatedAt: response.generated_at,
    engineVersion: response.engine_version,
    sourceParam: sourceParamOf(result),
  };
}

/**
 * Converts one batch calculation response into chart-ready line series, one
 * per enabled overlay — the boundary between the wire shape
 * (`IndicatorBatchResponse`) and what `CandlestickChart`'s `overlays` prop
 * expects, mirroring `data-adapter.ts`'s role for candle data. Reuses
 * `toUnixTime` rather than a second timestamp parser.
 *
 * An overlay whose indicator produced more than one series (a future
 * multi-series indicator — MACD, Bollinger Bands) is flattened to its
 * *first* series here: a single line per overlay row is this task's scope
 * ("chart overlay," not "chart panel"), and a multi-series indicator
 * remains fully usable on the standalone `/indicators` page's own chart.
 */
export function toOverlaySeries(
  response: IndicatorBatchResponse | undefined,
  overlays: readonly OverlayConfig[],
  colorFor: (overlay: OverlayConfig) => string,
): OverlayChartSeries[] {
  if (!response) {
    return [];
  }
  const timestamps = response.timestamps
    .map((iso) => toUnixTime(iso))
    .filter((time): time is NonNullable<typeof time> => time !== null);

  const byIndicator = new Map(response.results.map((result) => [result.indicator, result]));

  return overlays
    .filter((overlay) => overlay.enabled)
    .map((overlay) => {
      const result = byIndicator.get(overlay.indicator);
      const color = colorFor(overlay);
      const meta = metaFor(response, result);
      if (!result || !result.success || !result.series || result.series.length === 0) {
        return {
          id: overlay.id,
          label: overlay.label,
          color,
          data: [],
          ok: false,
          error: result?.error_detail ?? 'No result for this overlay.',
          meta,
        };
      }
      const values = result.series[0]!.values;
      const data: LineData[] = [];
      for (let index = 0; index < timestamps.length && index < values.length; index += 1) {
        const value = values[index];
        if (value !== null && value !== undefined) {
          data.push({ time: timestamps[index]!, value });
        }
      }
      return { id: overlay.id, label: overlay.label, color, data, ok: true, meta };
    });
}

interface OverlaySeriesCacheEntry {
  result: IndicatorBatchItemResult | undefined;
  color: string;
  series: OverlayChartSeries;
}

/**
 * Creates a memoizing wrapper around `toOverlaySeries`, keyed by overlay
 * id: an overlay whose batch result *reference* and resolved color are
 * both unchanged from the previous call returns the exact same
 * `OverlayChartSeries` object (including the same `data` array reference)
 * rather than a structurally-equal new one.
 *
 * This is what lets `CandlestickChart`'s Overlay Engine skip a redraw for
 * an unaffected overlay even though the *whole* batch response is a new
 * object on every fetch: TanStack Query's default structural sharing
 * already keeps an unchanged result's object reference stable across
 * refetches when its content is deep-equal, so "only the overlay whose
 * indicator/params actually changed gets a new `data` reference" holds
 * end-to-end — from "only modified indicators are recalculated" at the
 * engine/cache level, through to "only modified overlays are redrawn" at
 * the chart level.
 *
 * One cache belongs to one chart (created once via `useMemo`/`useRef` in
 * `useChartOverlays`) — never shared across charts, since two charts could
 * legitimately want different colors for the same overlay id.
 */
export function createOverlaySeriesCache() {
  const cache = new Map<string, OverlaySeriesCacheEntry>();

  return function toMemoizedOverlaySeries(
    response: IndicatorBatchResponse | undefined,
    overlays: readonly OverlayConfig[],
    colorFor: (overlay: OverlayConfig) => string,
  ): OverlayChartSeries[] {
    const liveIds = new Set(overlays.filter((overlay) => overlay.enabled).map((o) => o.id));
    for (const id of cache.keys()) {
      if (!liveIds.has(id)) {
        cache.delete(id);
      }
    }

    if (!response) {
      return [];
    }
    const byIndicator = new Map(response.results.map((result) => [result.indicator, result]));

    return overlays
      .filter((overlay) => overlay.enabled)
      .map((overlay) => {
        const result = byIndicator.get(overlay.indicator);
        const color = colorFor(overlay);
        const cached = cache.get(overlay.id);
        if (cached && cached.result === result && cached.color === color) {
          return cached.series;
        }
        const [series] = toOverlaySeries(response, [overlay], colorFor);
        cache.set(overlay.id, { result, color, series: series! });
        return series!;
      });
  };
}
