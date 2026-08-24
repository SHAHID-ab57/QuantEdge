import { describe, expect, it } from 'vitest';
import type { IndicatorBatchResponse } from '@/types/api/indicators';
import type { OverlayConfig } from '../store/use-overlay-store';
import { createOverlaySeriesCache, toOverlaySeries } from './overlay-series';

function overlay(overrides: Partial<OverlayConfig> = {}): OverlayConfig {
  return {
    id: 'overlay-1',
    indicator: 'sma',
    label: 'SMA(20)',
    params: { period: '20' },
    enabled: true,
    colorIndex: 0,
    ...overrides,
  };
}

function response(overrides: Partial<IndicatorBatchResponse> = {}): IndicatorBatchResponse {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z', '2026-01-01T02:00:00Z'],
    results: [
      {
        indicator: 'sma',
        success: true,
        label: 'Simple Moving Average',
        parameters: { period: 20 },
        series: [{ name: 'sma', label: 'SMA(20)', values: [null, 100, 110] }],
        cache_status: 'miss',
        warmup_candles: 1,
        execution_time_ms: 0.05,
        error_code: null,
        error_detail: null,
      },
    ],
    candles_analyzed: 3,
    database_time_ms: 1.2,
    engine_version: '1.0.0',
    generated_at: '2026-01-01T02:00:00Z',
    ...overrides,
  };
}

const color = () => '#2196f3';

describe('toOverlaySeries', () => {
  it('returns an empty list when there is no response yet', () => {
    expect(toOverlaySeries(undefined, [overlay()], color)).toEqual([]);
  });

  it('skips a disabled overlay', () => {
    const series = toOverlaySeries(response(), [overlay({ enabled: false })], color);
    expect(series).toEqual([]);
  });

  it('converts a successful result into line data, skipping null (warmup) points', () => {
    const series = toOverlaySeries(response(), [overlay()], color);
    expect(series).toHaveLength(1);
    expect(series[0]!.ok).toBe(true);
    expect(series[0]!.data).toHaveLength(2); // the leading null is dropped, not plotted as zero
    expect(series[0]!.data[0]!.value).toBe(100);
    expect(series[0]!.data[1]!.value).toBe(110);
  });

  it('uses the overlay’s own label and the supplied color, not the response’s', () => {
    const series = toOverlaySeries(
      response(),
      [overlay({ label: 'My Custom Label' })],
      () => '#ff0000',
    );
    expect(series[0]!.label).toBe('My Custom Label');
    expect(series[0]!.color).toBe('#ff0000');
  });

  it('reports a failed overlay as not-ok with its error detail, and no data', () => {
    const withError = response({
      results: [
        {
          indicator: 'sma',
          success: false,
          label: null,
          parameters: null,
          series: null,
          cache_status: null,
          warmup_candles: null,
          execution_time_ms: null,
          error_code: 'invalid_indicator_parameter',
          error_detail: "Parameter 'period' must be >= 1, got 0",
        },
      ],
    });
    const series = toOverlaySeries(withError, [overlay()], color);
    expect(series[0]!.ok).toBe(false);
    expect(series[0]!.data).toEqual([]);
    expect(series[0]!.error).toBe("Parameter 'period' must be >= 1, got 0");
  });

  it('reports an overlay missing from the batch response as not-ok', () => {
    const series = toOverlaySeries(response({ results: [] }), [overlay()], color);
    expect(series[0]!.ok).toBe(false);
  });

  it('produces one series per enabled overlay, preserving order', () => {
    const multi = response({
      results: [
        {
          indicator: 'sma',
          success: true,
          label: 'SMA',
          parameters: { period: 20 },
          series: [{ name: 'sma', label: 'SMA(20)', values: [100, 110, 120] }],
          cache_status: 'miss',
          warmup_candles: 0,
          execution_time_ms: 0.02,
          error_code: null,
          error_detail: null,
        },
        {
          indicator: 'ema',
          success: true,
          label: 'EMA',
          parameters: { period: 20 },
          series: [{ name: 'ema', label: 'EMA(20)', values: [101, 111, 121] }],
          cache_status: 'miss',
          warmup_candles: 0,
          execution_time_ms: 0.02,
          error_code: null,
          error_detail: null,
        },
      ],
    });
    const overlays = [
      overlay({ id: 'a', indicator: 'sma' }),
      overlay({ id: 'b', indicator: 'ema', colorIndex: 1 }),
    ];
    const series = toOverlaySeries(multi, overlays, color);
    expect(series.map((entry) => entry.id)).toEqual(['a', 'b']);
  });

  it('aligns data to whichever of timestamps/values is shorter, without throwing', () => {
    const short = response({
      timestamps: ['2026-01-01T00:00:00Z'],
      results: [
        {
          indicator: 'sma',
          success: true,
          label: 'SMA',
          parameters: {},
          series: [{ name: 'sma', label: 'SMA(20)', values: [100, 110, 120] }],
          cache_status: 'miss',
          warmup_candles: 0,
          execution_time_ms: 0.02,
          error_code: null,
          error_detail: null,
        },
      ],
    });
    const series = toOverlaySeries(short, [overlay()], color);
    expect(series[0]!.data).toHaveLength(1);
  });
});

describe('createOverlaySeriesCache', () => {
  it('returns the same series object when the result and color are unchanged', () => {
    const cache = createOverlaySeriesCache();
    const first = cache(response(), [overlay()], color);
    const second = cache(response(), [overlay()], color);
    // Two different `response()` calls produce structurally-equal but
    // distinct result objects; the cache is only exercised meaningfully
    // when a caller reuses the same result reference (the real-world case,
    // via TanStack Query's structural sharing) — so pass the identical
    // response object through both calls to isolate that.
    const shared = response();
    const third = cache(shared, [overlay()], color);
    const fourth = cache(shared, [overlay()], color);
    expect(third[0]).toBe(fourth[0]);
    expect(first[0]).not.toBe(second[0]); // sanity: distinct inputs are not coincidentally cached
  });

  it('recomputes only the overlay whose result reference actually changed', () => {
    const cache = createOverlaySeriesCache();
    const shared = response({
      results: [
        {
          indicator: 'sma',
          success: true,
          label: 'SMA',
          parameters: { period: 20 },
          series: [{ name: 'sma', label: 'SMA(20)', values: [100, 110] }],
          cache_status: 'miss',
          warmup_candles: 0,
          execution_time_ms: 0.01,
          error_code: null,
          error_detail: null,
        },
        {
          indicator: 'ema',
          success: true,
          label: 'EMA',
          parameters: { period: 20 },
          series: [{ name: 'ema', label: 'EMA(20)', values: [101, 111] }],
          cache_status: 'miss',
          warmup_candles: 0,
          execution_time_ms: 0.01,
          error_code: null,
          error_detail: null,
        },
      ],
    });
    const overlays = [
      overlay({ id: 'a', indicator: 'sma' }),
      overlay({ id: 'b', indicator: 'ema', colorIndex: 1 }),
    ];

    const first = cache(shared, overlays, color);

    // Only the `sma` result gets a new reference — as a real batch refetch
    // that changed one overlay's parameters would produce via structural
    // sharing (an unaffected result keeps its old reference).
    const partiallyChanged: IndicatorBatchResponse = {
      ...shared,
      results: [
        {
          ...shared.results[0]!,
          series: [{ ...shared.results[0]!.series![0]!, values: [200, 210] }],
        },
        shared.results[1]!,
      ],
    };
    const second = cache(partiallyChanged, overlays, color);

    expect(second[0]).not.toBe(first[0]); // sma changed
    expect(second[1]).toBe(first[1]); // ema unchanged — same object, not just equal
  });

  it('recomputes when the resolved color changes even if the result is unchanged', () => {
    const cache = createOverlaySeriesCache();
    const shared = response();
    const first = cache(shared, [overlay()], () => '#111111');
    const second = cache(shared, [overlay()], () => '#222222');
    expect(second[0]).not.toBe(first[0]);
    expect(second[0]!.color).toBe('#222222');
  });

  it('drops a removed overlay from its cache instead of growing forever', () => {
    const cache = createOverlaySeriesCache();
    const shared = response();
    cache(shared, [overlay({ id: 'a' })], color);
    // `a` is gone now; re-adding an overlay with the same id later must not
    // accidentally reuse a stale cached entry from before it was removed.
    const afterRemoval = cache(shared, [], color);
    expect(afterRemoval).toEqual([]);
    const readded = cache(shared, [overlay({ id: 'a' })], color);
    expect(readded[0]!.id).toBe('a');
  });
});
