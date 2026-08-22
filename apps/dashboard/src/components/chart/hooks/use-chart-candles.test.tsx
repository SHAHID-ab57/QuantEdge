import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { Candle, CandlePage } from '@/types/api/market';
import { MAX_CHART_CANDLES, useChartCandles } from './use-chart-candles';

vi.mock('@/lib/api/market', () => ({
  fetchCandlePage: vi.fn(),
}));

const mocked = vi.mocked(marketApi);

function candle(openTime: string): Candle {
  return {
    open_time: openTime,
    close_time: openTime,
    open: '100',
    high: '110',
    low: '90',
    close: '105',
    volume: '10',
    source: 'delta',
  };
}

function page(items: Candle[], total: number, offset: number): CandlePage {
  return {
    symbol: 'ETHUSD',
    timeframe: '1h',
    items,
    pagination: {
      total,
      returned: items.length,
      has_more: offset + items.length < total,
      limit: 1000,
      offset,
    },
    statistics: {
      highest_price: null,
      lowest_price: null,
      highest_volume: null,
      lowest_volume: null,
      average_open: null,
      average_close: null,
      average_high: null,
      average_low: null,
      average_volume: null,
      total_candles: total,
      first_candle_at: null,
      last_candle_at: null,
      expected_candles: total,
      missing_candles: 0,
      completeness: 100,
    },
    quality: {
      completeness_score: 100,
      freshness_score: 100,
      missing_interval_count: 0,
      missing_intervals: [],
      duplicate_candles: 0,
      out_of_order_candles: 0,
      invalid_ohlc_candles: 0,
      gaps_detected: false,
      overall_quality_score: 100,
    },
    meta: {
      execution_time_ms: 1,
      database_time_ms: 1,
      rows_scanned: items.length,
      rows_returned: items.length,
      cache_status: 'disabled',
      generated_at: '2026-08-01T00:00:00Z',
    },
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChartCandles', () => {
  it('is disabled until both a symbol and timeframe are selected', () => {
    const { result } = renderHook(() => useChartCandles({ symbol: null, timeframe: '1h' }), {
      wrapper,
    });
    expect(result.current.isPending).toBe(true);
    expect(mocked.fetchCandlePage).not.toHaveBeenCalled();
  });

  it('returns the single page as-is when the range fits in one request', async () => {
    // dir=desc, so the mock returns newest-first — the hook must reverse it.
    const items = [candle('2026-08-01T01:00:00Z'), candle('2026-08-01T00:00:00Z')];
    mocked.fetchCandlePage.mockResolvedValue(page(items, 2, 0));

    const { result } = renderHook(() => useChartCandles({ symbol: 'ETHUSD', timeframe: '1h' }), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked.fetchCandlePage).toHaveBeenCalledTimes(1);
    expect(mocked.fetchCandlePage).toHaveBeenCalledWith(
      'ETHUSD',
      '1h',
      expect.objectContaining({ limit: 1000, offset: 0, sort: 'open_time', dir: 'desc' }),
    );
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.truncated).toBe(false);
    // Pages are requested desc (newest-first) and reversed to ascending for the chart.
    expect(result.current.data?.candles.map((c) => c.open_time)).toEqual([
      '2026-08-01T00:00:00Z',
      '2026-08-01T01:00:00Z',
    ]);
  });

  it('paginates multiple pages and merges them in ascending order', async () => {
    const total = 1_500;
    // Minute candles counting backward from a fixed instant so offset 0 is
    // the newest 1000 and offset 1000 is the oldest 500 — exactly what a
    // dir=desc paginated fetch would return page by page.
    mocked.fetchCandlePage.mockImplementation((_symbol, _timeframe, params) => {
      const offset = params?.offset ?? 0;
      const remaining = Math.min(1000, total - offset);
      const items = Array.from({ length: remaining }, (_, index) =>
        candle(new Date(Date.UTC(2026, 0, 1) - (offset + index) * 60_000).toISOString()),
      );
      return Promise.resolve(page(items, total, offset));
    });

    const { result } = renderHook(() => useChartCandles({ symbol: 'ETHUSD', timeframe: '1m' }), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked.fetchCandlePage).toHaveBeenCalledTimes(2);
    expect(result.current.data?.total).toBe(total);
    expect(result.current.data?.truncated).toBe(false);
    const times = result.current.data!.candles.map((c) => Date.parse(c.open_time));
    expect(times).toHaveLength(total);
    for (let index = 1; index < times.length; index += 1) {
      expect(times[index]).toBeGreaterThan(times[index - 1]!);
    }
  });

  it('caps the fetched candle count and marks the result as truncated', async () => {
    const total = MAX_CHART_CANDLES + 5_000;
    mocked.fetchCandlePage.mockImplementation((_symbol, _timeframe, params) => {
      const offset = params?.offset ?? 0;
      const remaining = Math.min(1000, total - offset);
      const items = Array.from({ length: remaining }, (_, index) =>
        candle(new Date(Date.UTC(2026, 0, 1) - (offset + index) * 60_000).toISOString()),
      );
      return Promise.resolve(page(items, total, offset));
    });

    const { result } = renderHook(() => useChartCandles({ symbol: 'ETHUSD', timeframe: '1m' }), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.truncated).toBe(true);
    expect(result.current.data?.candles).toHaveLength(MAX_CHART_CANDLES);
    // 10 requests of 1000 candles each cover MAX_CHART_CANDLES.
    expect(mocked.fetchCandlePage).toHaveBeenCalledTimes(MAX_CHART_CANDLES / 1000);
  });
});
