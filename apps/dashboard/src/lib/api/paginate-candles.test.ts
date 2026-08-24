import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Candle, CandlePage } from '@/types/api/market';
import { fetchAllCandles } from './paginate-candles';

vi.mock('./market', () => ({ fetchCandlePage: vi.fn() }));

const { fetchCandlePage } = await import('./market');
const mockedFetch = vi.mocked(fetchCandlePage);

function candle(openTime: string): Candle {
  return {
    open_time: openTime,
    close_time: openTime,
    open: '1',
    high: '1',
    low: '1',
    close: '1',
    volume: '1',
    source: 'test',
  };
}

function page(items: Candle[], total: number): CandlePage {
  return {
    items,
    pagination: { total, returned: items.length, has_more: false, limit: items.length, offset: 0 },
    statistics: {
      total_candles: total,
      expected_candles: total,
      missing_candles: 0,
      completeness: 100,
    },
    quality: {
      freshness_score: 100,
      overall_quality_score: 100,
      duplicate_candles: 0,
      out_of_order_candles: 0,
      invalid_ohlc_candles: 0,
    },
  } as unknown as CandlePage;
}

const query = { symbol: 'ETHUSD', timeframe: '1m', limit: 2 };

beforeEach(() => {
  mockedFetch.mockReset();
});

describe('fetchAllCandles', () => {
  it('returns every candle from a single page when it covers the whole total', async () => {
    mockedFetch.mockResolvedValueOnce(page([candle('t1'), candle('t2')], 2));
    const result = await fetchAllCandles(query);
    expect(result.candles).toHaveLength(2);
    expect(result.truncated).toBe(false);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('walks multiple pages via offset until the reported total is reached', async () => {
    mockedFetch
      .mockResolvedValueOnce(page([candle('t1'), candle('t2')], 4))
      .mockResolvedValueOnce(page([candle('t3'), candle('t4')], 4));
    const result = await fetchAllCandles(query);
    expect(result.candles.map((c) => c.open_time)).toEqual(['t1', 't2', 't3', 't4']);
    expect(mockedFetch).toHaveBeenCalledTimes(2);
    expect(mockedFetch.mock.calls[1]?.[2]).toMatchObject({ offset: 2 });
  });

  it('stops early if a page returns fewer items than expected, rather than looping forever', async () => {
    mockedFetch.mockResolvedValueOnce(page([], 100));
    const result = await fetchAllCandles(query);
    expect(result.candles).toEqual([]);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('reports truncated once maxPages is hit, without fetching further', async () => {
    mockedFetch
      .mockResolvedValueOnce(page([candle('t1'), candle('t2')], 100))
      .mockResolvedValueOnce(page([candle('t3'), candle('t4')], 100));
    const result = await fetchAllCandles(query, undefined, 2);
    expect(result.candles).toHaveLength(4);
    expect(result.truncated).toBe(true);
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it('reports progress after every page fetched', async () => {
    mockedFetch
      .mockResolvedValueOnce(page([candle('t1'), candle('t2')], 4))
      .mockResolvedValueOnce(page([candle('t3'), candle('t4')], 4));
    const onProgress = vi.fn();
    await fetchAllCandles(query, onProgress);
    expect(onProgress).toHaveBeenNthCalledWith(1, 2, 4);
    expect(onProgress).toHaveBeenNthCalledWith(2, 4, 4);
  });

  it('returns the first page response for callers that need its pagination/quality metadata', async () => {
    const firstPage = page([candle('t1')], 1);
    mockedFetch.mockResolvedValueOnce(firstPage);
    const result = await fetchAllCandles(query);
    expect(result.firstPage).toBe(firstPage);
  });
});
